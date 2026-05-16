"""Pure computation engine for sensitivity analysis.

Contains the :class:`SensitivityResult` data class and the core
perturbation loop.  Depends on :mod:`prepare` for inputs and
:mod:`model.param` for parameter mutation.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from fdtr.analysis.sensitivity.prepare import (
    SensitivityInputs,
    build_sweep_spec,
    compute_signal,
)
from fdtr.input.config import FitConfig
from fdtr.model.layer import MultilayerStack
from fdtr.model.param import ResolvedParam, get_param_value


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityResult:
    mode: str
    signal: str
    axis_name: str
    axis_values: np.ndarray
    parameter_names: list[str]
    curves: dict[str, np.ndarray]
    delta: float
    baseline_zero_count: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def run_sensitivity_engine(
    inputs: SensitivityInputs,
    config: FitConfig,
) -> SensitivityResult:
    """Run the sensitivity perturbation loop over prepared inputs.

    This is a pure-computation function — no I/O or plotting.
    """
    sweep = inputs.sweep
    baseline = inputs.baseline

    baseline_scale = max(1.0, float(np.nanmax(np.abs(baseline))))
    zero_mask = np.abs(baseline) <= (1e-12 * baseline_scale)

    curves: dict[str, np.ndarray] = {}
    for param in inputs.params:
        p0 = get_param_value(inputs.stack, param.raw_name, spot_size_um=inputs.spot_size_um)
        if p0 == 0.0:
            raise ValueError(
                f"Sensitivity parameter '{param.raw_name}' has zero-valued "
                f"baseline and cannot be perturbed."
            )

        plus_stack, plus_spot = _apply_param_perturbation(
            inputs.stack, inputs.spot_size_um, param, p0 * (1.0 + inputs.delta),
        )
        minus_stack, minus_spot = _apply_param_perturbation(
            inputs.stack, inputs.spot_size_um, param, p0 * (1.0 - inputs.delta),
        )

        plus_signal = np.asarray(
            compute_signal(config, plus_stack, plus_spot, sweep), dtype=float,
        )
        minus_signal = np.asarray(
            compute_signal(config, minus_stack, minus_spot, sweep), dtype=float,
        )

        curve = np.full(baseline.shape, np.nan, dtype=float)
        valid = ~zero_mask
        curve[valid] = (
            ((plus_signal[valid] - minus_signal[valid]) / baseline[valid])
            / (2.0 * inputs.delta)
        )
        curves[param.raw_name] = curve

    return SensitivityResult(
        mode=sweep.mode,
        signal=config.signal,
        axis_name=sweep.axis_name,
        axis_values=sweep.axis_values,
        parameter_names=[param.raw_name for param in inputs.params],
        curves=curves,
        delta=inputs.delta,
        baseline_zero_count=int(np.count_nonzero(zero_mask)),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_param_perturbation(
    stack: MultilayerStack,
    spot_size_um: float,
    param: ResolvedParam,
    value: float,
) -> tuple[MultilayerStack, float]:
    """Return a new (stack, spot_size_um) with *param* set to *value*."""
    if param.kind == "spot_size":
        return stack, float(value)

    layers = [dataclasses.replace(layer) for layer in stack.layers]

    if param.kind in {"S", "TBC"}:
        layers[param.layer_index] = dataclasses.replace(
            layers[param.layer_index],
            Sr=value,
            Sz=value,
        )
        return MultilayerStack(layers), float(spot_size_um)

    layers[param.layer_index] = dataclasses.replace(
        layers[param.layer_index],
        **{param.property_name: value},
    )
    return MultilayerStack(layers), float(spot_size_um)
