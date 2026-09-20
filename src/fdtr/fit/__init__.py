"""Fitting engine: parameter estimation strategies."""

from fdtr.common_types import FitResult, FitTarget, SignalType
from fdtr.fit.freq_fitter import FreqFitter
from fdtr.fit.offset_fitter import OffsetFitter
from fdtr.fit.fwhm_fitter import FWHMFitter
from fdtr.model.param import ResolvedParam, apply_params, resolve, validate_targets


def __getattr__(name):
    """Lazy re-exports to avoid circular imports."""
    if name in ("FitConfig", "LayerSpec", "TargetSpec"):
        from fdtr.input import config as _config
        return getattr(_config, name)
    if name == "ReportGenerator":
        from fdtr.output.report import ReportGenerator
        return ReportGenerator
    if name in ("PipelineSpec", "StepSpec", "PipelineRunner", "PipelineResult"):
        from fdtr.fit import iterfit as _iterfit
        return getattr(_iterfit, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FreqFitter",
    "FWHMFitter",
    "FitConfig", "FitResult", "FitTarget",
    "LayerSpec",
    "OffsetFitter",
    "PipelineResult", "PipelineRunner", "PipelineSpec", "StepSpec",
    "ReportGenerator",
    "ResolvedParam", "SignalType",
    "TargetSpec",
    "apply_params", "resolve", "validate_targets",
]
