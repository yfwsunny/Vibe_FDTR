"""Shared offset-center calculations."""

from __future__ import annotations

import warnings

import numpy as np
from scipy.optimize import curve_fit


def center_amp_key_for_offset_data(data_key: str) -> str | None:
    """Return the companion center-amplitude key for an offset phase data key."""
    if data_key.endswith("_phase"):
        return f"{data_key[:-len('_phase')]}_center_amp"
    return None


def resolve_center_amp(
    offset_data: np.ndarray,
    signal_data: np.ndarray,
    *,
    center_offset_data: np.ndarray | None = None,
    center_amp_data: np.ndarray | None = None,
) -> np.ndarray:
    """Return center amplitude on the same offset grid as signal data."""
    offset_data = np.asarray(offset_data, dtype=np.float64).ravel()
    signal_data = np.asarray(signal_data, dtype=np.float64).ravel()
    if center_amp_data is None:
        return signal_data

    center_amp = np.asarray(center_amp_data, dtype=np.float64).ravel()
    if center_offset_data is None:
        if center_amp.shape != signal_data.shape:
            raise ValueError("center_amp_data must match signal_data shape.")
        return center_amp

    center_offset = np.asarray(center_offset_data, dtype=np.float64).ravel()
    if center_offset.shape != center_amp.shape:
        raise ValueError("center_offset_data must match center_amp_data shape.")
    return np.interp(offset_data, center_offset, center_amp)


def estimate_offset_center(
    offset_data: np.ndarray,
    center_amp_data: np.ndarray,
    *,
    dense_points: int = 1001,
    warn: bool = True,
) -> float:
    """Estimate the offset-scan center from a local Gaussian amplitude peak."""
    offset_data = np.asarray(offset_data, dtype=np.float64).ravel()
    center_amp_data = np.asarray(center_amp_data, dtype=np.float64).ravel()

    def warn_failed() -> None:
        if warn:
            warnings.warn(
                "Offset center estimation failed; using center_offset=0.",
                UserWarning,
                stacklevel=3,
            )

    if len(offset_data) < 5 or offset_data.shape != center_amp_data.shape or np.ptp(center_amp_data) <= 0:
        warn_failed()
        return 0.0

    peak_value = float(np.max(center_amp_data))
    tie_tol = max(np.finfo(float).eps * max(abs(peak_value), 1.0) * 32.0, 1e-12)
    peak_mask = np.isclose(center_amp_data, peak_value, rtol=0.0, atol=tie_tol)
    peak_indices = np.flatnonzero(peak_mask)
    peak_idx = int(peak_indices[0])
    peak_x = float(np.mean(offset_data[peak_indices]))
    window = np.abs(offset_data - peak_x) <= 3.0
    if np.count_nonzero(window) < 5:
        lo = max(0, peak_idx - 4)
        hi = min(len(offset_data), peak_idx + 5)
        window = np.zeros(len(offset_data), dtype=bool)
        window[lo:hi] = True

    x = offset_data[window]
    y = center_amp_data[window]
    if len(x) < 5 or np.ptp(y) <= 0:
        warn_failed()
        return 0.0

    def gaussian(xv, amp, x0, sigma, baseline):
        return baseline + amp * np.exp(-0.5 * ((xv - x0) / sigma) ** 2)

    amp0 = float(np.max(y) - np.min(y))
    baseline0 = float(np.min(y))
    sigma0 = max(float((x.max() - x.min()) / 4.0), 1e-6)
    try:
        popt, _ = curve_fit(
            gaussian,
            x,
            y,
            p0=[amp0, peak_x, sigma0, baseline0],
            bounds=([0.0, x.min(), 1e-9, -np.inf], [np.inf, x.max(), np.inf, np.inf]),
            maxfev=5000,
        )
        dense_x = np.linspace(float(x.min()), float(x.max()), max(11, int(dense_points)))
        dense_y = gaussian(dense_x, *popt)
        return float(dense_x[int(np.argmax(dense_y))])
    except (RuntimeError, ValueError, FloatingPointError):
        warn_failed()
        return 0.0
