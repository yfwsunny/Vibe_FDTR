"""Consolidated fit-plotting functions for FDTR toolkit.

Each function accepts raw data + config + result, generates the model curve
internally, and returns a matplotlib Figure.  All figure creation goes through
``output.plots.create_figure`` so styling is consistent.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from fdtr.common_types import SignalType
from fdtr.output.fit_curve_cal import (
    FitCurve,
    calculate_freq_fit_curve,
    calculate_offset_fit_curve,
    calculate_spot_fit_curve,
)
from fdtr.output.plots import create_figure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_fit_title(ax, result) -> None:
    """Add a title summarising fitted values and residual to *ax*."""
    parts = [f"{k} = {v:.4g}" for k, v in result.fitted_values.items()]
    parts.append(f"Residual = {result.residual:.4f}")
    ax.set_title(", ".join(parts))


# ---------------------------------------------------------------------------
# Freq-sweep fit
# ---------------------------------------------------------------------------

def plot_freq_fit(
    freq_data: np.ndarray,
    signal_data: np.ndarray,
    config,
    result,
    max_points: int | None = None,
    curve: FitCurve | None = None,
) -> Figure:
    """Plot freq-sweep data vs fitted model curve.

    Parameters
    ----------
    freq_data : array
        Measured frequency array (Hz).
    signal_data : array
        Measured signal (phase in degrees or amplitude).
    config : FitConfig
        Configuration (used for spot_size, signal type).
    result : FitResult
        Fit result (fitted_stack, fitted_values, residual).
    max_points : int or None, optional
        If set, subsample the data to at most this many points (evenly
        spaced in index) before plotting.  Useful when the dataset is
        large and the scatter plot becomes too dense or slow.

    Returns
    -------
    Figure
    """
    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE
    curve = curve or calculate_freq_fit_curve(freq_data, signal_data, config, result, max_points=max_points)
    if signal == SignalType.PHASE:
        ylabel = "Phase (degrees)"
    else:
        ylabel = "Amplitude (normalized)"

    fig, ax = create_figure()
    ax.scatter(curve.x, curve.data, c="blue", s=20, alpha=0.7, label="Data", zorder=3)
    ax.plot(curve.x, curve.model, "r-", linewidth=1.5, label="Fit", zorder=2)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(ylabel)
    ax.legend()
    _add_fit_title(ax, result)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Offset fit
# ---------------------------------------------------------------------------

def plot_offset_fit(
    sep_um: np.ndarray,
    signal_data: np.ndarray,
    freq: float,
    config,
    result,
    max_points: int | None = None,
    curve: FitCurve | None = None,
) -> Figure:
    """Plot offset-scan data vs fitted model curve.

    Handles phase centering (subtract zero-offset phase) and amplitude
    normalisation (subtract peak, normalise to [-1, 1]).

    Parameters
    ----------
    sep_um : array
        Measured offset positions (um).
    signal_data : array
        Measured signal (phase in degrees or amplitude).
    freq : float
        Frequency used for the fit (Hz).
    config : FitConfig
        Configuration (spot_size, signal type).
    result : FitResult
        Fit result with fitted_stack.

    Returns
    -------
    Figure
    """
    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE
    curve = curve or calculate_offset_fit_curve(sep_um, signal_data, freq, config, result, max_points=max_points)

    if signal == SignalType.PHASE:
        fig, ax = create_figure()
        ax.scatter(curve.x, curve.data, c="blue", s=20, alpha=0.7, label="Data", zorder=3)
        ax.plot(curve.x, curve.model, "r-", linewidth=1.5, label="Fit", zorder=2)
        ax.set_xlabel("Offset (um)")
        ax.set_ylabel("Phase (degrees)")
        ax.legend()
        _add_fit_title(ax, result)
        fig.tight_layout()
        return fig

    fig, ax = create_figure()
    ax.scatter(curve.x, curve.data, c="blue", s=20, alpha=0.7, label="Data", zorder=3)
    ax.plot(curve.x, curve.model, "r-", linewidth=1.5, label="Fit", zorder=2)
    ax.set_xlabel("Offset (um)")
    ax.set_ylabel("Amplitude (normalized, centered)")
    ax.legend()
    _add_fit_title(ax, result)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Spot (FWHM) fit
# ---------------------------------------------------------------------------

def plot_spot_fit(
    sep_um: np.ndarray,
    amp_data: np.ndarray,
    stack,
    spot_size: float,
    freq: float,
    result,
    direction: str = "",
    max_points: int | None = None,
    curve: FitCurve | None = None,
) -> Figure:
    """Plot spot-fit amplitude data vs fitted model curve.

    Evaluates h2d at each offset position for the model curve and normalises
    both data and model to [0, 1].

    Parameters
    ----------
    sep_um : array
        Measured offset positions (um).
    amp_data : array
        Measured amplitude data.
    stack : MultilayerStack
        Layer stack used for h2d evaluation.
    spot_size : float
        Fitted spot size (um).
    freq : float
        Frequency (Hz).
    result : FitResult
        Fit result (fitted_values, residual).
    direction : str
        Optional direction label (e.g. " (X)").
    max_points : int or None, optional
        If set, subsample the data to at most this many points (evenly
        spaced in index) before plotting.  Useful when the dataset is
        large and the scatter plot becomes too dense or slow.

    Returns
    -------
    Figure
    """
    curve = curve or calculate_spot_fit_curve(sep_um, amp_data, stack, spot_size, freq, max_points=max_points)

    fig, ax = create_figure()
    ax.scatter(curve.x, curve.data, c="blue", s=20, alpha=0.7, label="Data", zorder=3)
    ax.plot(curve.x, curve.model, "r-", linewidth=1.5, label="Fit", zorder=2)
    ax.set_xlabel("Offset (um)")
    ax.set_ylabel("Amplitude (normalized)")
    ax.legend()
    ax.set_title(f"Spot Fit{direction}: w = {spot_size:.3f} um, Residual = {result.residual:.4f}")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# CSV writers (companion to each plot function)
# ---------------------------------------------------------------------------

def write_freq_fit_csv(
    freq_data: np.ndarray,
    signal_data: np.ndarray,
    model_signal: np.ndarray,
    path: Path,
    signal_name: str = "phase",
) -> Path:
    """Write freq-sweep data and model to CSV."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    col = signal_name
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frequency_hz", f"data_{col}", f"model_{col}"])
        for i in range(len(freq_data)):
            writer.writerow([
                f"{float(freq_data[i]):.12g}",
                f"{float(signal_data[i]):.12g}",
                f"{float(model_signal[i]):.12g}",
            ])
    return path


def write_offset_fit_csv(
    sep_um: np.ndarray,
    signal_data: np.ndarray,
    model_signal: np.ndarray,
    path: Path,
    signal_name: str = "phase",
) -> Path:
    """Write offset-scan data and model to CSV."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    col = signal_name
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["offset_um", f"data_{col}", f"model_{col}"])
        for i in range(len(sep_um)):
            writer.writerow([
                f"{float(sep_um[i]):.12g}",
                f"{float(signal_data[i]):.12g}",
                f"{float(model_signal[i]):.12g}",
            ])
    return path


def write_spot_fit_csv(
    sep_um: np.ndarray,
    amp_data: np.ndarray,
    model_amp: np.ndarray,
    path: Path,
) -> Path:
    """Write spot-fit amplitude data and model to CSV."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["offset_um", "data_amplitude", "model_amplitude"])
        for i in range(len(sep_um)):
            writer.writerow([
                f"{float(sep_um[i]):.12g}",
                f"{float(amp_data[i]):.12g}",
                f"{float(model_amp[i]):.12g}",
            ])
    return path
