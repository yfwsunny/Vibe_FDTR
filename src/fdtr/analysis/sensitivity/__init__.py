"""Sensitivity analysis module.

Public API is re-exported from the new flat modules:
* :mod:`prepare` — input preparation
* :mod:`engine` — pure computation
* :mod:`output` — CSV / plot writing
* :mod:`run_sensitivity` — top-level orchestration
"""

# Backward-compatible re-exports from new modules.
from fdtr.analysis.sensitivity.engine import SensitivityResult
from fdtr.analysis.sensitivity.output import (
    SensitivityArtifacts,
    handle_sensitivity_output,
)
from fdtr.analysis.sensitivity.prepare import (
    SensitivityInputs,
    SweepSpec,
    build_sweep_spec,
    compute_signal,
    prepare_sensitivity,
    resolve_sensitivity_params,
)
from fdtr.analysis.sensitivity.run_sensitivity import run_sensitivity

# Re-exported from model.param for convenience
from fdtr.model.param import (
    ResolvedParam,
    default_parameter_names,
    get_param_value,
    resolve,
)

__all__ = [
    # New public API
    "SensitivityArtifacts",
    "SensitivityInputs",
    "SensitivityResult",
    "SweepSpec",
    "build_sweep_spec",
    "compute_signal",
    "handle_sensitivity_output",
    "prepare_sensitivity",
    "resolve_sensitivity_params",
    "run_sensitivity",
    # Re-exported from model.param for convenience
    "ResolvedParam",
    "default_parameter_names",
    "get_param_value",
    "resolve",
]
