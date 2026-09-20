"""init-config subcommand: generate template TOML config."""

from __future__ import annotations

import sys
import tomllib

from pathlib import Path

from fdtr.input.config import normalize_strategy, to_toml
from fdtr.input.config._toml_utils import parse_ranges
from fdtr.input.config.analysis_template import (
    analysis_dict_to_toml_string,
    build_analysis_from_args,
)
from fdtr.input.config.config_request import InitConfigRequest
from fdtr.input.config.config_template import build_fit_config
from fdtr.input.config.prepare_spot import average_directional_spots
from fdtr.input.config.unit_check import (
    UnitCheckError,
    check_init_config_units,
    check_uncertainty_known_params,
)


def run_init_config(args) -> None:
    """Generate a template TOML config file."""
    analysis = getattr(args, "analysis", "none")

    if analysis != "none":
        _run_analysis_config(args)
        return

    req = _args_to_request(args)
    cfg = build_fit_config(req)
    mode = "full" if req.full_template else "lean"

    from fdtr.output import OutputPaths, get_material_names, resolve_task_root
    from fdtr.output.paths import derive_group_slug

    material_names = get_material_names(cfg)
    group_key = cfg.group_key or ((req.paths_spec or {}).get("group_key") if req.paths_spec else None)
    inherited_from = getattr(args, "paths_spec", None)
    task_dir = resolve_task_root(
        inherited_from=inherited_from,
        material_names=material_names,
        group_key=group_key,
    )
    command = {
        "freqfit": "freq",
        "offsetfit": "offset",
        "spotfit": "spot",
        "iterfit": "iter",
    }.get(req.strategy, "iter")
    group_slug = derive_group_slug(group_key=group_key, material_names=material_names)
    paths = OutputPaths(base=task_dir, command=command, suffix=group_slug)
    config_path = paths.next_config_path()
    to_toml(cfg, config_path, mode=mode)
    _trim_generated_template(config_path, mode=mode)
    print(f"Config written to {config_path}")
    _print_material_summary(cfg)


def _print_material_summary(cfg) -> None:
    """Print a compact one-line summary of resolved material properties."""
    parts = []
    for layer in cfg.layers:
        if layer.rho_cp == 0:
            continue
        name = layer.material or layer.name
        parts.append(f"{name} Sr={layer.Sr:.1f} Sz={layer.Sz:.1f}")
    if parts:
        print("Resolved: " + " | ".join(parts))


def _args_to_request(args) -> InitConfigRequest:
    """Convert argparse namespace to InitConfigRequest."""
    strategy = args.strategy
    if strategy is None:
        print("Error: --strategy is required for base config generation", file=sys.stderr)
        sys.exit(1)
    strategy = normalize_strategy(strategy)
    if not (getattr(args, "transducer", None) or "").strip():
        print("Error: --transducer is required for base config generation", file=sys.stderr)
        sys.exit(1)
    if not (getattr(args, "substrate", None) or "").strip():
        print("Error: --substrate is required for base config generation", file=sys.stderr)
        sys.exit(1)
    try:
        transducer, transducer_thickness = InitConfigRequest.parse_material_spec(args.transducer)
        substrate, substrate_thickness = InitConfigRequest.parse_material_spec(args.substrate)
        if substrate_thickness is not None:
            raise ValueError("Substrate inline thickness is not supported.")
        layers, layer_thicknesses = _parse_layer_specs(getattr(args, "layer", None) or [])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    fit_entries = getattr(args, "fit", None) or []
    fit_params = InitConfigRequest.parse_fit_entries(fit_entries) if fit_entries else {}

    paths_spec = _load_paths_spec(args)
    freq_ranges = parse_ranges(getattr(args, "freq_range", None))
    offset_ranges = parse_ranges(getattr(args, "offset_range", None))
    try:
        spot_size, spot_x, spot_y = _resolve_spot_args(
            strategy,
            getattr(args, "spot_size", None),
            getattr(args, "spot_x", None),
            getattr(args, "spot_y", None),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        check_init_config_units(
            transducer_thickness=transducer_thickness,
            layer_thicknesses=layer_thicknesses,
            spot_size=spot_size,
            spot_x=spot_x,
            spot_y=spot_y,
            freq_offset=getattr(args, "freq_offset", None),
            freq_spot=getattr(args, "freq_spot", None),
            freq_ranges=freq_ranges,
            offset_ranges=offset_ranges,
            fit_params=fit_params,
            mode="error",
        )
    except UnitCheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    return InitConfigRequest(
        transducer=transducer,
        substrate=substrate,
        strategy=strategy,
        layers=layers,
        transducer_thickness=transducer_thickness,
        layer_thicknesses=layer_thicknesses,
        temperature=getattr(args, "temperature", 295.15),
        fit_params=fit_params,
        paths_spec=paths_spec,
        spot_size=spot_size,
        spot_x=spot_x,
        spot_y=spot_y,
        freq_offset=getattr(args, "freq_offset", None) or 1.194e6,
        freq_spot=getattr(args, "freq_spot", None) or 5.0e7,
        signal=getattr(args, "signal", None) or "phase",
        offset_points=getattr(args, "offset_points", None) or 100,
        phase_points=getattr(args, "phase_points", None) or 80,
        freq_ranges=freq_ranges,
        offset_ranges=offset_ranges,
        pipeline=getattr(args, "pipeline", None),
        iterations=getattr(args, "iterations", None) or 6,
        full_template=getattr(args, "full_template", False),
    )


def _resolve_spot_args(
    strategy: str,
    spot_size: float | None,
    spot_x: float | None,
    spot_y: float | None,
) -> tuple[float, float | None, float | None]:
    """Resolve init-config spot fields.

    Normal configs should carry only ``spot_size``. Directional fields are
    emitted only when both axes are provided, which marks an explicit
    directional spot workflow.
    """
    if spot_x is not None and spot_y is not None:
        avg = average_directional_spots(spot_x, spot_y)
        if spot_size is not None and abs(float(spot_size) - avg) > 1e-12:
            raise ValueError(
                "--spot-size must equal the average of --spot-x and --spot-y "
                "when directional spot fields are provided."
            )
        return avg, spot_x, spot_y
    if strategy == "iterfit" and spot_size is not None:
        if spot_x is not None:
            return spot_size, spot_x, None
        if spot_y is not None:
            return spot_size, None, spot_y
    if spot_size is not None:
        return spot_size, None, None
    if spot_x is not None:
        return spot_x, None, None
    if spot_y is not None:
        return spot_y, None, None
    return 3.0, None, None


def _parse_layer_specs(raw_layers: list[str]) -> tuple[list[str], list[float | None]]:
    """Parse repeatable layer specs into material names and optional thicknesses."""
    layers: list[str] = []
    thicknesses: list[float | None] = []
    for raw in raw_layers:
        material, thickness = InitConfigRequest.parse_material_spec(raw)
        layers.append(material)
        thicknesses.append(thickness)
    return (layers, thicknesses)


def _load_paths_spec(args) -> dict | None:
    """Load structured path input from file or inline JSON."""
    if getattr(args, "paths_spec", None) and getattr(args, "paths_json", None):
        print("Error: use only one of --paths-spec or --paths-json", file=sys.stderr)
        sys.exit(1)
    if getattr(args, "paths_spec", None):
        return InitConfigRequest.load_paths_spec_file(args.paths_spec)
    if getattr(args, "paths_json", None):
        return InitConfigRequest.load_paths_spec_json(args.paths_json)
    return None


def _run_analysis_config(args) -> None:
    """Generate a flat analysis TOML config file."""
    base_config = getattr(args, "base_config", None)
    if not base_config:
        print("Error: --base-config is required when --analysis is not 'none'", file=sys.stderr)
        sys.exit(1)

    d = build_analysis_from_args(args)
    try:
        check_init_config_units(
            spot_size=d.get("spot_size"),
            spot_x=d.get("spot_x"),
            spot_y=d.get("spot_y"),
            freq_offset=d.get("freq_offset"),
            freq_spot=d.get("freq_spot"),
            freq_ranges=d.get("freq_ranges"),
            offset_ranges=d.get("offset_ranges"),
            mode="error",
        )
    except UnitCheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    check_uncertainty_known_params(d.get("known_params"), mode="warning")
    toml_str = analysis_dict_to_toml_string(d)

    output = _default_analysis_output_path(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(toml_str, encoding="utf-8")
    print(f"Config written to {output}")


def _trim_generated_template(path: str | Path, *, mode: str) -> None:
    """Remove init-config defaults that should stay implicit in generated TOML."""
    config_path = Path(path)
    lines = config_path.read_text(encoding="utf-8").splitlines()
    filtered = [
        line
        for line in lines
        if not line.strip().startswith("average = true")
    ]
    if mode == "lean":
        compacted: list[str] = []
        previous_blank = False
        for line in filtered:
            if line.strip():
                compacted.append(line.rstrip())
                previous_blank = False
            elif not previous_blank:
                compacted.append("")
                previous_blank = True
        filtered = compacted
    config_path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")


def _default_analysis_output_path(args) -> Path:
    """Choose the default output path for a generated analysis config."""
    base_config = Path(args.base_config).resolve()
    analysis_kind = getattr(args, "analysis", "analysis")
    strategy = normalize_strategy(getattr(args, "strategy", None) or "iterfit")
    from fdtr.output import OutputPaths, resolve_task_root
    from fdtr.output.paths import derive_group_slug_from_config

    material_names = _material_names_from_base_config(base_config)
    task_root = resolve_task_root(
        inherited_from=base_config,
        material_names=material_names,
        config_path=base_config,
    )
    command = {
        "freqfit": "freq",
        "offsetfit": "offset",
        "spotfit": "spot",
        "iterfit": "iter",
    }.get(strategy, strategy)
    command = f"{analysis_kind}_{command}"
    group_slug = derive_group_slug_from_config(base_config)
    return OutputPaths(base=task_root, command=command, suffix=group_slug).next_config_path()


def _material_names_from_base_config(base_config: Path) -> list[str]:
    """Read the top/bottom material names from an existing base config TOML."""
    from fdtr.output import get_material_names_from_dict

    try:
        raw = tomllib.loads(base_config.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []
    return get_material_names_from_dict(raw)
