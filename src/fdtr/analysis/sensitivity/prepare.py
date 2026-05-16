"""Input preparation for sensitivity analysis.

Consolidates parameter resolution, sweep spec generation, and baseline
signal computation from the former ``sensitivity_params`` and
``sensitivity_signals`` modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from fdtr.input.config import FitConfig, SensitivitySpec, to_stack
from fdtr.model.h2d import h2d
from fdtr.model.layer import MultilayerStack
from fdtr.model.param import ResolvedParam, default_parameter_names, resolve

_DEFAULT_FREQ_RANGE = (5.0e4, 2.0e7)
_DEFAULT_OFFSET_RANGE = (-15.0, 15.0)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SweepSpec:
    mode: str
    axis_name: str
    axis_values: np.ndarray


@dataclass(frozen=True)
class SensitivityInputs:
    """Fully resolved inputs ready for the sensitivity engine."""
    stack: MultilayerStack
    params: list[ResolvedParam]
    sweep: SweepSpec
    baseline: np.ndarray
    delta: float
    spot_size_um: float


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

def resolve_sensitivity_params(
    requested: Sequence[str] | None,
    stack: MultilayerStack,
) -> list[ResolvedParam]:
    """Resolve requested parameter names to :class:`ResolvedParam` objects.

    Uses :func:`model.param.resolve` for each name after expanding ``"all"``.
    """
    names = list(requested or ["all"])
    if not names:
        names = ["all"]

    if "all" in names and len(names) > 1:
        raise ValueError("Cannot mix 'all' with explicit sensitivity parameter names.")

    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        dup_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate sensitivity parameter names are not allowed: {dup_list}.")

    if names == ["all"]:
        names = default_parameter_names(stack)

    return [resolve(name, stack) for name in names]


# ---------------------------------------------------------------------------
# Sweep spec
# ---------------------------------------------------------------------------

def build_sweep_spec(config: FitConfig) -> SweepSpec:
    strategy = config.strategy

    if strategy == "freqfit":
        ranges = config.freq_ranges
        if not ranges:
            ranges = [_DEFAULT_FREQ_RANGE]

        n_points = int(config.phase_points)
        axis = np.concatenate(
            [np.logspace(np.log10(lo), np.log10(hi), n_points) for lo, hi in ranges]
        )
        return SweepSpec(mode="freq", axis_name="frequency_Hz", axis_values=axis)

    if strategy == "offsetfit":
        ranges = config.offset_ranges
        if not ranges:
            ranges = [_DEFAULT_OFFSET_RANGE]

        axis = _build_piecewise_linear_axis(ranges, int(config.offset_points))
        return SweepSpec(mode="offset", axis_name="offset_um", axis_values=axis)

    raise ValueError(
        f"Sensitivity sweep generation requires strategy 'freqfit' or 'offsetfit', got '{config.strategy}'."
    )


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signal(
    config: FitConfig,
    stack: MultilayerStack,
    spot_size_um: float,
    sweep: SweepSpec,
) -> np.ndarray:
    w = spot_size_um * 1e-6

    if sweep.mode == "freq":
        omega = 2.0 * np.pi * sweep.axis_values
        response = h2d(omega, w0=w, w1=w, sep=0.0, stack=stack)
    elif sweep.mode == "offset":
        if config.freq_offset is None:
            raise ValueError("Offset sensitivity requires config.freq_offset to be set.")
        omega = np.array([2.0 * np.pi * config.freq_offset], dtype=float)
        response = h2d(
            omega,
            w0=w,
            w1=w,
            sep=sweep.axis_values * 1e-6,
            stack=stack,
        ).reshape(-1)
    else:
        raise ValueError(f"Unsupported sweep mode '{sweep.mode}'.")

    if config.signal == "phase":
        phase = np.angle(response)
        if np.ndim(phase) >= 1 and phase.size > 1:
            phase = np.unwrap(phase)
        return np.degrees(phase)
    if config.signal == "amplitude":
        return np.abs(response)
    raise ValueError(f"Unsupported sensitivity signal '{config.signal}'.")


# ---------------------------------------------------------------------------
# Top-level preparation
# ---------------------------------------------------------------------------

def prepare_sensitivity(config: FitConfig) -> SensitivityInputs:
    """Build all inputs required by the sensitivity engine.

    Returns a :class:`SensitivityInputs` containing the resolved stack,
    parameter list, sweep spec, baseline signal, and configuration.
    """
    sensitivity = config.sensitivity or SensitivitySpec()

    if config.spot_size is None:
        raise ValueError("Sensitivity analysis requires config.spot_size to be set.")
    if not (0.0 < sensitivity.delta < 1.0):
        raise ValueError("Sensitivity delta must satisfy 0.0 < delta < 1.0.")

    stack = to_stack(config)
    params = resolve_sensitivity_params(sensitivity.parameters, stack)
    sweep = build_sweep_spec(config)
    baseline = np.asarray(compute_signal(config, stack, config.spot_size, sweep), dtype=float)

    return SensitivityInputs(
        stack=stack,
        params=params,
        sweep=sweep,
        baseline=baseline,
        delta=sensitivity.delta,
        spot_size_um=config.spot_size,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_piecewise_linear_axis(
    ranges: Sequence[tuple[float, float]],
    n_points: int,
) -> np.ndarray:
    normalized = sorted((min(lo, hi), max(lo, hi)) for lo, hi in ranges)
    if not normalized:
        raise ValueError("At least one offset range is required.")

    if len(normalized) == 1:
        lo, hi = normalized[0]
        return np.linspace(lo, hi, n_points)

    if n_points < 2 * len(normalized):
        raise ValueError(
            f"Need at least {2 * len(normalized)} points to sample {len(normalized)} offset ranges."
        )

    lengths = np.array([hi - lo for lo, hi in normalized], dtype=float)
    total_length = float(lengths.sum())

    if total_length == 0.0:
        counts = np.full(len(normalized), 2, dtype=int)
    else:
        raw = lengths / total_length * n_points
        counts = np.maximum(2, np.floor(raw).astype(int))

    diff = int(n_points - counts.sum())
    if diff > 0:
        if total_length == 0.0:
            order = list(range(len(normalized)))
        else:
            fractional = raw - np.floor(raw)
            order = list(np.argsort(-fractional))
        for i in range(diff):
            counts[order[i % len(order)]] += 1
    elif diff < 0:
        if total_length == 0.0:
            order = list(range(len(normalized)))
        else:
            order = list(np.argsort(-(lengths / np.maximum(counts, 1))))
        remaining = -diff
        idx = 0
        while remaining > 0:
            target = order[idx % len(order)]
            if counts[target] > 2:
                counts[target] -= 1
                remaining -= 1
            idx += 1

    pieces = [
        np.linspace(lo, hi, int(count))
        for (lo, hi), count in zip(normalized, counts, strict=True)
    ]
    return np.concatenate(pieces)
