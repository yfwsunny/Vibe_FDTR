"""Pipeline specification data model and TOML I/O for iterative fitting."""

from __future__ import annotations

import logging
import tomllib
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_FITTERS = frozenset({"fwhm", "freq", "offset"})
_VALID_SIGNALS = frozenset({"phase", "amplitude"})
_VALID_SPOT_KEYS = frozenset({"spot_x", "spot_y", "spot_size", "none"})
_BUILTIN_PIPELINE_PREFIX = "builtin:"
_DEFAULT_BUILTIN_PIPELINE = "builtin:default"


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


def validate_pipeline(
    pipeline: PipelineSpec,
    datasets: Dict[str, Tuple[np.ndarray, np.ndarray]],
    stack,
) -> List[str]:
    """Validate a :class:`PipelineSpec` against loaded data and layer stack.

    Returns a list of error strings.  An empty list means the pipeline is valid.
    """
    from fdtr.model.param import resolve

    errors: list[str] = []

    # Rule 1: minimum steps
    if len(pipeline.steps) < 2:
        errors.append(
            f"Pipeline must have at least 2 steps, got {len(pipeline.steps)}."
        )

    # Rule 9: convergence_tol
    if pipeline.convergence_tol <= 0:
        errors.append("convergence_tol must be positive.")

    available_keys = sorted(datasets.keys())

    for step in pipeline.steps:
        prefix = f"Step '{step.name}'"

        # Rule 2: required fields
        if not step.name:
            errors.append(f"{prefix} is missing required field: name")
        if not step.fitter:
            errors.append(f"{prefix} is missing required field: fitter")
        if not step.data_key:
            errors.append(f"{prefix} is missing required field: data_key")
        if not step.target_names:
            errors.append(f"{prefix} is missing required field: target_names")

        # Rule 3: fitter enum
        if step.fitter and step.fitter not in _VALID_FITTERS:
            errors.append(
                f"{prefix} has unknown fitter '{step.fitter}'. "
                f"Must be: {', '.join(sorted(_VALID_FITTERS))}"
            )

        # Rule 4: data_key existence
        if step.data_key and step.data_key not in datasets:
            errors.append(
                f"{prefix} references data_key '{step.data_key}' not found in "
                f"loaded datasets. Available: {', '.join(available_keys)}"
            )

        # Rule 5: signal required for freq/offset
        if step.fitter in ("freq", "offset") and not step.signal:
            errors.append(
                f"{prefix} (fitter='{step.fitter}') requires 'signal' to be set."
            )

        # Rule 6: signal enum
        if step.signal is not None and step.signal not in _VALID_SIGNALS:
            errors.append(
                f"{prefix} has unknown signal '{step.signal}'. "
                f"Must be: {', '.join(sorted(_VALID_SIGNALS))}"
            )

        # Rule 7: spot_key enum
        if step.spot_key and step.spot_key not in _VALID_SPOT_KEYS:
            errors.append(
                f"{prefix} has unknown spot_key '{step.spot_key}'. "
                f"Must be: {', '.join(sorted(_VALID_SPOT_KEYS))}"
            )

        # Rule 8: target_names vs layer stack
        for target_name in step.target_names:
            try:
                resolve(target_name, stack)
            except ValueError as exc:
                errors.append(f"{prefix} has invalid target '{target_name}': {exc}")

    return errors


def load_default_pipeline() -> PipelineSpec:
    """Load the built-in default pipeline from ``default.toml``."""
    default_path = Path(__file__).parent / "default.toml"
    return load_pipeline(default_path)


def is_builtin_pipeline_reference(value: str | None) -> bool:
    """Return True when *value* references a built-in pipeline."""
    return bool(value) and value.startswith(_BUILTIN_PIPELINE_PREFIX)


def load_builtin_pipeline(reference: str) -> PipelineSpec:
    """Load a built-in pipeline from a ``builtin:...`` reference."""
    if reference == _DEFAULT_BUILTIN_PIPELINE:
        return load_default_pipeline()
    if reference == "default":
        raise ValueError(
            'pipeline = "default" is no longer supported; use "builtin:default".'
        )
    raise ValueError(
        f"Unknown built-in pipeline '{reference}'. Use 'builtin:default' or a pipeline file path."
    )


def resolve_pipeline_for_config(config) -> PipelineSpec:
    """Resolve a pipeline with target names valid for *config*'s layer symmetry."""
    from fdtr.input.config.config_build import to_stack
    from fdtr.input.config.path_resolution import resolve_config_path
    from fdtr.model.param import resolve

    pipeline_name = getattr(config, "pipeline", None) or _DEFAULT_BUILTIN_PIPELINE
    stack = to_stack(config)

    if pipeline_name == "default":
        raise ValueError(
            'pipeline = "default" is no longer supported; use "builtin:default".'
        )
    if is_builtin_pipeline_reference(pipeline_name):
        pipeline = _rewrite_default_pipeline_for_symmetry(
            load_builtin_pipeline(pipeline_name),
            stack,
        )
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
# Internal: dict -> dataclass conversion
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
