"""Init-config template generation: build FitConfig from InitConfigRequest."""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path
from typing import Any

from fdtr.input.config.config_build import (
    apply_fit_fields,
    build_layers_from_materials,
)
from fdtr.input.config.config_dataclass import FitConfig, LayerSpec, TargetSpec
from fdtr.input.config.config_request import InitConfigRequest


def build_fit_config(req: InitConfigRequest) -> FitConfig:
    """Build a complete FitConfig from an InitConfigRequest.

    This is the core generation function. CLI, batch, and Python API
    callers all produce an InitConfigRequest and call this function.
    """
    layers = build_layers_from_materials(
        transducer=req.transducer,
        substrate=req.substrate,
        intermediate=req.layers or None,
        transducer_thickness=req.transducer_thickness,
        layer_thicknesses=req.layer_thicknesses or None,
        temperature=req.temperature,
    )

    cfg = FitConfig(
        temperature=req.temperature,
        layers=layers,
        strategy=req.strategy,
        spot_size=req.spot_size,
        pipeline=req.pipeline,
    )

    fit_params = req.fit_params
    if req.strategy == "iterfit":
        fit_params = _filter_iterfit_fit_params(req, fit_params, cfg)

    apply_fit_fields(cfg, req.strategy, fit_params=fit_params)
    if req.strategy == "iterfit":
        _restrict_iterfit_targets_to_pipeline(cfg, req)
        _autofill_iterfit_pipeline_targets(cfg, req)

    _apply_paths_spec(cfg, req)
    freq_spot, freq_offset = _resolve_scan_frequencies(req)

    # Paths
    if req.offset_dir is not None:
        cfg.offset_dir = req.offset_dir
    if req.phase_dir is not None:
        cfg.phase_dir = req.phase_dir
    if req.data_file is not None:
        cfg.data_file = req.data_file
    if req.data_file_y is not None:
        cfg.data_file_y = req.data_file_y
    if req.offset_dir_y is not None:
        cfg.offset_dir_y = req.offset_dir_y
    if req.offset_pattern is not None:
        cfg.offset_pattern = req.offset_pattern
    if req.offset_pattern_y is not None:
        cfg.offset_pattern_y = req.offset_pattern_y
    if req.phase_pattern is not None:
        cfg.phase_pattern = req.phase_pattern
    if req.offset_files is not None:
        cfg.offset_files = req.offset_files
    if req.offset_files_y is not None:
        cfg.offset_files_y = req.offset_files_y
    if req.phase_files is not None:
        cfg.phase_files = req.phase_files
    if req.output_dir is not None:
        cfg.output_dir = req.output_dir

    # Fit settings
    cfg.freq_offset = freq_offset
    cfg.freq_spot = freq_spot
    cfg.signal = req.signal
    cfg.offset_points = req.offset_points
    cfg.phase_points = req.phase_points
    cfg.no_plot = req.no_plot
    cfg.average = req.average
    _needs_freq = req.strategy in ("freqfit", "iterfit")
    _needs_offset = req.strategy in ("offsetfit", "spotfit", "iterfit")
    if req.freq_ranges is not None:
        cfg.freq_ranges = req.freq_ranges
    elif cfg.freq_ranges is None and _needs_freq:
        cfg.freq_ranges = _auto_freq_ranges(req)
    if req.offset_ranges is not None:
        cfg.offset_ranges = req.offset_ranges
    elif cfg.offset_ranges is None and _needs_offset:
        cfg.offset_ranges = _auto_offset_ranges(req)
    if req.pipeline is not None:
        cfg.pipeline = req.pipeline
    if req.iterations != 6:
        cfg.iterations = req.iterations

    cfg.report = req.report

    return cfg


def _filter_iterfit_fit_params(
    req: InitConfigRequest,
    fit_params: dict[str, tuple[float, float]],
    cfg: FitConfig | None = None,
) -> dict[str, tuple[float, float]]:
    """Keep only fit params referenced by the iterfit pipeline."""
    supported_names = set(_iterfit_pipeline_target_names(req, cfg))
    ignored = sorted(name for name in fit_params if name not in supported_names)
    if ignored:
        warnings.warn(
            "Ignoring fit targets not used by iterfit pipeline: "
            + ", ".join(ignored),
            stacklevel=2,
        )
    return {name: bounds for name, bounds in fit_params.items() if name in supported_names}


def _autofill_iterfit_pipeline_targets(cfg: FitConfig, req: InitConfigRequest) -> None:
    """Ensure every iterfit pipeline target has bounds in the generated config."""
    from fdtr.input.config import resolve_guess

    target_names = _iterfit_pipeline_target_names(req, cfg)
    existing_names = _config_target_spec_names(cfg)
    added: list[str] = []

    for name in target_names:
        if name in existing_names:
            continue
        guess = resolve_guess(cfg, TargetSpec(name=name, bounds=(0.0, 0.0)))
        bounds = _auto_bounds_from_guess(name, guess)
        _apply_target_bounds(cfg, name, bounds)
        existing_names.add(name)
        added.append(f"{name}=[{bounds[0]:.6g}, {bounds[1]:.6g}]")

    if added:
        warnings.warn(
            "Added missing iterfit targets from pipeline with auto bounds: "
            + ", ".join(added),
            stacklevel=2,
        )


def _restrict_iterfit_targets_to_pipeline(cfg: FitConfig, req: InitConfigRequest) -> None:
    """Drop generated iterfit targets that are not referenced by the pipeline."""
    supported_names = set(_iterfit_pipeline_target_names(req, cfg))

    if "spot_size" not in supported_names:
        cfg.fit_spot_size = None
    if "spot_x" not in supported_names:
        cfg.fit_spot_x = None
    if "spot_y" not in supported_names:
        cfg.fit_spot_y = None

    for idx, layer in enumerate(cfg.layers):
        kept_fields: dict[str, tuple[float, float]] = {}
        for prop, bounds in layer.fit_fields.items():
            name = f"TBC_{idx}" if prop == "TBC" else f"{prop}_{idx}"
            if name in supported_names:
                kept_fields[prop] = bounds
        if kept_fields != layer.fit_fields:
            cfg.layers[idx] = dataclasses.replace(layer, fit_fields=kept_fields)

    cfg.targets = [target for target in cfg.targets if target.name in supported_names]


def _iterfit_pipeline_target_names(req: InitConfigRequest, cfg: FitConfig | None = None) -> list[str]:
    """Load target names from the configured iterfit pipeline in step order."""
    from fdtr.fit.iterfit import load_default_pipeline, load_pipeline, resolve_pipeline_for_config

    if cfg is not None:
        pipeline = resolve_pipeline_for_config(cfg)
    else:
        pipeline_name = req.pipeline or "default"
        pipeline = load_default_pipeline() if pipeline_name == "default" else load_pipeline(pipeline_name)

    names: list[str] = []
    seen: set[str] = set()
    for step in pipeline.steps:
        for target_name in step.target_names:
            if target_name not in seen:
                seen.add(target_name)
                names.append(target_name)
    return names


def _config_target_spec_names(cfg: FitConfig) -> set[str]:
    """Collect configured target names from layer, spot, and legacy sections."""
    names: set[str] = set()
    for i, layer in enumerate(cfg.layers):
        names.update(target.name for target in layer.to_targets(i))
    if cfg.fit_spot_size is not None:
        names.add("spot_size")
    if cfg.fit_spot_x is not None:
        names.add("spot_x")
    if cfg.fit_spot_y is not None:
        names.add("spot_y")
    names.update(target.name for target in cfg.targets)
    return names


def _auto_bounds_from_guess(name: str, guess: float) -> tuple[float, float]:
    """Build conservative auto bounds from the current parameter value."""
    scale = abs(float(guess))
    if scale == 0.0:
        scale = 1.0
        warnings.warn(
            f"Auto-bounding iterfit target '{name}' from zero guess; using fallback scale 1.0.",
            stacklevel=2,
        )
    return (scale * 0.1, scale * 10.0)


def _apply_target_bounds(
    cfg: FitConfig,
    name: str,
    bounds: tuple[float, float],
) -> None:
    """Write target bounds onto the correct config location."""
    if name == "spot_size":
        cfg.fit_spot_size = bounds
        return
    if name == "spot_x":
        cfg.fit_spot_x = bounds
        return
    if name == "spot_y":
        cfg.fit_spot_y = bounds
        return

    prop, idx_str = name.rsplit("_", 1)
    idx = int(idx_str)
    layer = cfg.layers[idx]
    fit_fields = dict(layer.fit_fields)
    fit_fields[prop] = bounds
    cfg.layers[idx] = dataclasses.replace(layer, fit_fields=fit_fields)


def _resolve_scan_frequencies(req: InitConfigRequest) -> tuple[float, float]:
    """Resolve spot/offset frequencies, using scanner hints when safe."""
    freq_spot = req.freq_spot
    freq_offset = req.freq_offset
    freqs = _offset_frequencies(req.paths_spec)
    if not freqs:
        return (freq_spot, freq_offset)

    default_spot = InitConfigRequest.freq_spot
    default_offset = InitConfigRequest.freq_offset

    if req.strategy == "spotfit" and freq_spot == default_spot:
        freq_spot = max(freqs)
    if req.strategy in {"spotfit", "offsetfit", "iterfit"} and freq_offset == default_offset:
        candidates = [freq for freq in freqs if freq != freq_spot]
        freq_offset = min(candidates or freqs)

    return (freq_spot, freq_offset)


def _offset_frequencies(spec: dict[str, Any] | None) -> list[float]:
    """Collect unique offset frequencies from scan-data path specs."""
    if not spec:
        return []

    values: set[float] = set()
    for key in ("offset_x", "offset_y"):
        section = spec.get(key) or {}
        for raw in section.get("offset_freqs_hz") or []:
            try:
                values.add(float(raw))
            except (TypeError, ValueError):
                continue
    return sorted(values)


def _apply_paths_spec(cfg: FitConfig, req: InitConfigRequest) -> None:
    """Apply structured path-spec input onto a FitConfig."""
    spec = req.paths_spec
    if not spec:
        return

    root_dir = spec.get("directory")
    offset_x = spec.get("offset_x") or {}
    offset_y = spec.get("offset_y") or {}
    freq_sweep = spec.get("freq_sweep") or {}

    offset_dir = offset_x.get("dir") or offset_x.get("directory") or root_dir
    offset_dir_y = offset_y.get("dir") or offset_y.get("directory")
    phase_dir = freq_sweep.get("dir") or freq_sweep.get("directory") or root_dir

    if offset_dir is not None:
        cfg.offset_dir = str(_resolve_spec_path(spec, offset_dir))
    if offset_dir_y is not None:
        cfg.offset_dir_y = str(_resolve_spec_path(spec, offset_dir_y))
    if phase_dir is not None:
        cfg.phase_dir = str(_resolve_spec_path(spec, phase_dir))
    if spec.get("group_key") is not None:
        cfg.group_key = str(spec["group_key"])

    if offset_x.get("file") is not None:
        cfg.data_file = str(offset_x["file"])
    if offset_y.get("file") is not None:
        cfg.data_file_y = str(offset_y["file"])

    if offset_x.get("pattern") is not None:
        cfg.offset_pattern = str(offset_x["pattern"])
    if offset_y.get("pattern") is not None:
        cfg.offset_pattern_y = str(offset_y["pattern"])
    if freq_sweep.get("pattern") is not None:
        cfg.phase_pattern = str(freq_sweep["pattern"])


def _resolve_spec_path(spec: dict, raw_path: str | Path) -> Path:
    """Resolve a path embedded in a paths-spec payload."""
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()

    source_path = spec.get("__source_path__")
    if source_path:
        source_file = Path(source_path).resolve()
        return (source_file.parent / path).resolve()

    return path.resolve()


_DEFAULT_FREQ_RANGE = (5e4, 2e7)
_DEFAULT_OFFSET_RANGE = (-15.0, 15.0)


def _auto_freq_ranges(req: InitConfigRequest) -> list[tuple[float, float]] | None:
    """Derive freq_ranges from scan-data paths spec, or return default."""
    spec = req.paths_spec
    if spec:
        freq_sweep = spec.get("freq_sweep") or {}
        f_min = freq_sweep.get("freq_min_hz")
        f_max = freq_sweep.get("freq_max_hz")
        if f_min is not None and f_max is not None:
            return [(float(f_min), float(f_max))]
    return [_DEFAULT_FREQ_RANGE]


def _auto_offset_ranges(req: InitConfigRequest) -> list[tuple[float, float]] | None:
    """Derive offset_ranges from scan-data paths spec, or return default."""
    spec = req.paths_spec
    if spec:
        for key in ("offset_x", "offset_y"):
            section = spec.get(key) or {}
            o_min = section.get("offset_min_um")
            o_max = section.get("offset_max_um")
            if o_min is not None and o_max is not None:
                return [(float(o_min), float(o_max))]
    return [_DEFAULT_OFFSET_RANGE]
