"""Pipeline specification data model and TOML I/O for iterative fitting."""

from __future__ import annotations

import tomllib
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class StepSpec:
    """Specification for one step in an iterative fitting pipeline.

    Attributes:
        name: Human-readable step name.
        fitter: Fitter engine to use — ``"fwhm"``, ``"freq"``, or ``"offset"``.
        signal: Signal channel — ``"phase"`` or ``"amplitude"``.
            Required for ``freq`` and ``offset`` fitters; ``None`` for ``fwhm``.
        data_key: Key in the ``datasets`` dict passed to the runner.
        target_names: Parameter names to fit in this step.
    """

    name: str
    fitter: str  # "fwhm" | "freq" | "offset"
    signal: Optional[str] = None  # "phase" | "amplitude"
    data_key: str = ""
    target_names: List[str] = field(default_factory=list)
    spot_key: str = "spot_size"  # "spot_x" | "spot_y" | "spot_size" | "none"
    freq_ranges: Optional[List[Tuple[float, float]]] = None
    offset_ranges: Optional[List[Tuple[float, float]]] = None
    freq_offset: Optional[float] = None


@dataclass(frozen=True)
class PipelineSpec:
    """Complete iterative fitting pipeline definition.

    Attributes:
        name: Pipeline name.
        steps: Ordered list of fitting steps executed per iteration.
        convergence_tol: Relative convergence tolerance (default 1e-4).
    """

    name: str
    steps: List[StepSpec] = field(default_factory=list)
    convergence_tol: float = 1e-4


# ---------------------------------------------------------------------------
# TOML I/O
# ---------------------------------------------------------------------------


def load_pipeline(path: str | Path) -> PipelineSpec:
    """Load a :class:`PipelineSpec` from a TOML file."""
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _from_dict(data)


def save_pipeline(spec: PipelineSpec, path: str | Path) -> None:
    """Write a :class:`PipelineSpec` to a TOML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml_string(spec), encoding="utf-8")


def load_default_pipeline() -> PipelineSpec:
    """Load the built-in default pipeline from ``default.toml``."""
    default_path = Path(__file__).parent / "default.toml"
    return load_pipeline(default_path)


def resolve_pipeline_for_config(config) -> PipelineSpec:
    """Resolve a pipeline with target names valid for *config*'s layer symmetry."""
    from fdtr.input.config.config_build import to_stack
    from fdtr.input.config.path_resolution import resolve_config_path
    from fdtr.model.param import resolve

    pipeline_name = getattr(config, "pipeline", None) or "default"
    stack = to_stack(config)

    if pipeline_name == "default":
        pipeline = _rewrite_default_pipeline_for_symmetry(load_default_pipeline(), stack)
    else:
        pipeline = load_pipeline(resolve_config_path(config, pipeline_name))

    for step in pipeline.steps:
        for target_name in step.target_names:
            resolve(target_name, stack)
    return pipeline


def _rewrite_default_pipeline_for_symmetry(
    pipeline: PipelineSpec,
    stack,
) -> PipelineSpec:
    """Rewrite Sr_N/Sz_N defaults to S_N only when that same layer is isotropic."""
    from fdtr.model.layer import SYMMETRY_ISOTROPIC

    new_steps: list[StepSpec] = []
    for step in pipeline.steps:
        rewritten: list[str] = []
        seen: set[str] = set()
        for target_name in step.target_names:
            replacement = target_name
            if target_name.startswith(("Sr_", "Sz_")):
                prefix, idx_text = target_name.split("_", 1)
                if idx_text.isdigit():
                    idx = int(idx_text)
                    if idx < stack.num_layers and stack.layers[idx].symmetry == SYMMETRY_ISOTROPIC:
                        replacement = f"S_{idx}"
            if replacement not in seen:
                rewritten.append(replacement)
                seen.add(replacement)
        new_steps.append(dataclasses.replace(step, target_names=rewritten))
    return dataclasses.replace(pipeline, name="default-isotropic" if any(
        "S_" in target for step in new_steps for target in step.target_names
    ) else pipeline.name, steps=new_steps)


# ---------------------------------------------------------------------------
# Internal: dict <-> dataclass conversion
# ---------------------------------------------------------------------------


def _from_dict(data: dict) -> PipelineSpec:
    """Construct a PipelineSpec from a parsed TOML dictionary."""
    steps: list[StepSpec] = []
    for sd in data.get("step", []):
        fr = sd.get("freq_ranges", None)
        if fr is not None:
            fr = [(float(r[0]), float(r[1])) for r in fr]
        odr = sd.get("offset_ranges", None)
        if odr is not None:
            odr = [(float(r[0]), float(r[1])) for r in odr]
        fo = sd.get("freq_offset", None)
        if fo is not None:
            fo = float(fo)
        steps.append(
            StepSpec(
                name=sd["name"],
                fitter=sd["fitter"],
                signal=sd.get("signal", None),
                data_key=sd.get("data_key", ""),
                target_names=list(sd.get("target_names", [])),
                spot_key=sd.get("spot_key", "spot_size"),
                freq_ranges=fr,
                offset_ranges=odr,
                freq_offset=fo,
            )
        )
    return PipelineSpec(
        name=data.get("name", "unnamed"),
        steps=steps,
        convergence_tol=data.get("convergence_tol", 1e-4),
    )


def _to_toml_string(spec: PipelineSpec) -> str:
    """Produce a TOML document string from a PipelineSpec."""
    lines: list[str] = []

    # Header comments
    lines.append(f"name = {_fmt_str(spec.name)}")
    lines.append(
        f"convergence_tol = {repr(spec.convergence_tol)}"
        "  # relative-change threshold for early stop"
    )
    lines.append("")
    lines.append("# Each [[step]] is one fitting operation. Steps run in order;")
    lines.append("# the pipeline repeats for config.iterations (or until convergence).")

    _fitter_desc = {
        "fwhm": "fit beam spot size via FWHM of offset scan",
        "freq": "fit parameters from frequency-sweep data",
        "offset": "fit parameters from beam-offset scan",
    }
    for step in spec.steps:
        desc = _fitter_desc.get(step.fitter, "fitting step")
        lines.append("")
        lines.append(f"[[step]]  # {desc}")
        _row(lines, "name", _fmt_str(step.name), "human-readable step label")
        _row(lines, "fitter", _fmt_str(step.fitter), '"fwhm" | "freq" | "offset"')
        if step.signal is not None:
            _row(lines, "signal", _fmt_str(step.signal), '"phase" | "amplitude"')
        _row(lines, "data_key", _fmt_str(step.data_key), "key in datasets dict")
        tgt = "[" + ", ".join(_fmt_str(t) for t in step.target_names) + "]"
        _row(lines, "target_names", tgt, "model parameters to fit")
        if step.spot_key != "spot_size":
            _row(lines, "spot_key", _fmt_str(step.spot_key), "which spot-size variable to use")
        if step.freq_ranges is not None:
            fr_str = ", ".join(f"[{r[0]}, {r[1]}]" for r in step.freq_ranges)
            _row(lines, "freq_ranges", f"[{fr_str}]", "Hz — step-level override")
        if step.offset_ranges is not None:
            or_str = ", ".join(f"[{r[0]}, {r[1]}]" for r in step.offset_ranges)
            _row(lines, "offset_ranges", f"[{or_str}]", "um — step-level override")
        if step.freq_offset is not None:
            _row(lines, "freq_offset", repr(step.freq_offset), "Hz — step-level override")
    lines.append("")  # trailing newline
    return "\n".join(lines)


def _row(lines: list[str], key: str, value: str, comment: str) -> None:
    """Append an aligned key = value  # comment line."""
    COL = 32  # column where the inline comment starts
    assignment = f"{key} = {value}"
    pad = max(1, COL - len(assignment))
    lines.append(f"{assignment}{' ' * pad}# {comment}")


def _fmt_str(s: str) -> str:
    return f'"{s}"'
