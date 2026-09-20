"""Shared fit-curve calculations for plots and CSV outputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from fdtr.common_types import SignalType
from fdtr.fit.offsetcenter_cal import estimate_offset_center, resolve_center_amp
from fdtr.model.h2d import h2d


@dataclass(frozen=True)
class FitCurve:
    """Calculated curve arrays shared by plot and CSV writers."""

    x: np.ndarray
    data: np.ndarray
    model: np.ndarray


def sample_curve_arrays(max_points: int | None, *arrays: np.ndarray) -> tuple[np.ndarray, ...]:
    """Apply index-based subsampling consistently across related arrays."""
    if not arrays:
        return ()
    first = np.asarray(arrays[0])
    if max_points is None or len(first) <= max_points:
        return tuple(np.asarray(arr) for arr in arrays)
    idx = np.linspace(0, len(first) - 1, max_points, dtype=int)
    return tuple(np.asarray(arr)[idx] for arr in arrays)


def calculate_freq_fit_curve(
    freq_data: np.ndarray,
    signal_data: np.ndarray,
    config,
    result,
    max_points: int | None = None,
) -> FitCurve:
    """Calculate frequency-sweep data/model values at the output frequencies."""
    freq_out, signal_out = sample_curve_arrays(max_points, freq_data, signal_data)
    if result.fitted_stack is None:
        model = np.full_like(signal_out, np.nan, dtype=float)
        return FitCurve(x=freq_out, data=signal_out, model=model)

    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE
    w_m = config.spot_size * 1e-6
    omega = 2.0 * np.pi * freq_out
    response = h2d(omega, w0=w_m, w1=w_m, sep=0.0, stack=result.fitted_stack)
    if signal == SignalType.PHASE:
        model = np.degrees(np.angle(response))
    else:
        model = np.abs(response)
    return FitCurve(x=freq_out, data=signal_out, model=np.asarray(model, dtype=float))


def calculate_offset_fit_curve(
    sep_um: np.ndarray,
    signal_data: np.ndarray,
    freq: float,
    config,
    result,
    max_points: int | None = None,
    center_amp_data: np.ndarray | None = None,
) -> FitCurve:
    """Calculate centered/normalized offset data/model values."""
    sep_um = np.asarray(sep_um, dtype=float).ravel()
    signal_data = np.asarray(signal_data, dtype=float).ravel()
    center_amp = resolve_center_amp(
        sep_um,
        signal_data,
        center_amp_data=center_amp_data,
    )

    center_offset = estimate_offset_center(sep_um, center_amp, warn=False)
    sort_idx = np.argsort(sep_um)
    data_center = float(PchipInterpolator(sep_um[sort_idx], signal_data[sort_idx])(center_offset))

    sep_out, signal_out = sample_curve_arrays(max_points, sep_um, signal_data)
    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE

    sep_centered = sep_out - center_offset

    if result.fitted_stack is None:
        model = np.full_like(signal_out, np.nan, dtype=float)
        data = signal_out - data_center if signal == SignalType.PHASE else signal_out
        return FitCurve(x=sep_centered, data=data, model=model)

    w_m = config.spot_size * 1e-6
    omega = np.atleast_1d(2.0 * np.pi * freq)
    response = h2d(omega, w0=w_m, w1=w_m, sep=sep_centered * 1e-6, stack=result.fitted_stack)
    resp = response[0] if np.ndim(response) > 1 else response

    if signal == SignalType.PHASE:
        phase_model = np.degrees(np.angle(resp))
        zero_response = h2d(omega, w0=w_m, w1=w_m, sep=np.array([0.0]), stack=result.fitted_stack)
        zero_resp = zero_response[0, 0] if np.ndim(zero_response) > 1 else np.ravel(zero_response)[0]
        model = phase_model - np.degrees(np.angle(zero_resp))
        data = signal_out - data_center
        return FitCurve(x=sep_centered, data=data, model=np.asarray(model, dtype=float))

    amp_model = np.abs(resp)
    amp_model_centered = amp_model - np.max(amp_model)
    amp_model_scale = np.max(np.abs(amp_model_centered))
    model = amp_model_centered / amp_model_scale if amp_model_scale > 0 else amp_model_centered

    amp_data_centered = signal_out - data_center
    amp_data_scale = np.max(np.abs(amp_data_centered))
    data = amp_data_centered / amp_data_scale if amp_data_scale > 0 else amp_data_centered
    return FitCurve(x=sep_centered, data=data, model=np.asarray(model, dtype=float))


def calculate_spot_fit_curve(
    sep_um: np.ndarray,
    amp_data: np.ndarray,
    stack,
    spot_size: float,
    freq: float,
    max_points: int | None = None,
) -> FitCurve:
    """Calculate normalized spot-fit amplitude data/model values."""
    sep_out, amp_out = sample_curve_arrays(max_points, sep_um, amp_data)
    w_m = spot_size * 1e-6
    omega = np.atleast_1d(2.0 * np.pi * freq)
    amp_model = np.array([
        np.abs(h2d(omega, w0=w_m, w1=w_m, sep=s * 1e-6, stack=stack)[0])
        for s in sep_out
    ])

    model_scale = np.max(np.abs(amp_model))
    data_scale = np.max(np.abs(amp_out))
    model = amp_model / model_scale if model_scale > 0 else amp_model
    data = amp_out / data_scale if data_scale > 0 else amp_out
    return FitCurve(x=sep_out, data=data, model=model)
