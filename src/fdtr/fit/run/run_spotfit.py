# src/fdtr/fit/run/run_spotfit.py
"""Orchestration runner for beam spot-size (FWHM) fitting."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

from fdtr.input.config import FitConfig, from_toml, to_stack, to_fit_targets
from fdtr.common_types import FitTarget, FitResult
from fdtr.fit.fwhm_fitter import FWHMFitter
from fdtr.input.dataloader.cli_data_loader import _load_offset_scan_data
from fdtr.output.cli_display import print_result
from fdtr.output.fit_plots import plot_spot_fit, write_spot_fit_csv
from fdtr.output.fit_curve_cal import calculate_spot_fit_curve
from fdtr.output.result_io import save_result
from fdtr.fit.run.postfit import resolve_fit_output_paths, handle_fit_exit
from fdtr.input.config.path_resolution import resolve_config_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_spot_target(config: FitConfig, axis: str | None = None) -> FitTarget:
    spot_targets = {
        t.name: t
        for t in to_fit_targets(config)
        if t.name in {"spot_size", "spot_x", "spot_y"}
    }
    if axis == "x":
        target = spot_targets.get("spot_x") or spot_targets.get("spot_size")
    elif axis == "y":
        target = spot_targets.get("spot_y") or spot_targets.get("spot_size")
    else:
        target = spot_targets.get("spot_size")
    if target is not None:
        return target
    guess = config.spot_size if config.spot_size is not None else 3.0
    name = f"spot_{axis}" if axis in {"x", "y"} else "spot_size"
    return FitTarget(name=name, initial_guess=guess, bounds=(0.3, 30.0))


def _resolve_spot_value(result: FitResult, fallback: float) -> float:
    for key in ("spot_size", "spot_x", "spot_y"):
        if key in result.fitted_values:
            return result.fitted_values[key]
    return fallback


def _print_spot_result(spot_x, spot_y, spot_avg, result_x, result_y):
    print("\n" + "=" * 50)
    print("  FDTR Spot-Only Fit Results")
    print("=" * 50)
    print(f"  {'spot_x':20s} = {spot_x:.4f} um")
    if spot_y is not None:
        print(f"  {'spot_y':20s} = {spot_y:.4f} um")
        print(f"  {'spot_size (avg)':20s} = {spot_avg:.4f} um")
    print("-" * 50)
    print(f"  {'Residual (X)':20s} = {result_x.residual:.6e}")
    if result_y is not None:
        print(f"  {'Residual (Y)':20s} = {result_y.residual:.6e}")
    print(f"  {'Converged (X)':20s} = {result_x.success}")
    if result_y is not None:
        print(f"  {'Converged (Y)':20s} = {result_y.success}")
    print("=" * 50 + "\n")


def _load_spot_scans(config, data_file_x, data_file_y):
    if data_file_x is not None:
        if not data_file_x.is_file():
            raise FileNotFoundError(f"Data file does not exist: {data_file_x}")
        scan_data_x = _load_offset_scan_data(
            data_file_x,
            average=config.average,
            n_points=config.offset_points,
        )
        if "X" in scan_data_x:
            scan_x = scan_data_x["X"]
        elif "Y" in scan_data_x:
            scan_x = scan_data_x["Y"]
        else:
            scan_x = scan_data_x[next(iter(scan_data_x))]
        scan_y = None
        if data_file_y is not None:
            if not data_file_y.is_file():
                raise FileNotFoundError(f"Y-scan data file does not exist: {data_file_y}")
            scan_data_y = _load_offset_scan_data(
                data_file_y,
                average=config.average,
                n_points=config.offset_points,
            )
            if "Y" in scan_data_y:
                scan_y = scan_data_y["Y"]
            elif "X" in scan_data_y:
                scan_y = scan_data_y["X"]
            else:
                scan_y = scan_data_y[next(iter(scan_data_y))]
        return data_file_x, data_file_y, scan_x, scan_y
    if config.offset_dir:
        data_dir = resolve_config_path(config, config.offset_dir)
        if not data_dir.is_dir():
            raise FileNotFoundError(f"Offset directory does not exist: {data_dir}")
        scan_data = _load_offset_scan_data(
            data_dir, average=config.average, n_points=config.offset_points,
            pattern=config.offset_pattern, explicit_files=config.offset_files,
        )
        if "X" in scan_data:
            x_key = "X"
        elif "Y" in scan_data:
            x_key = "Y"
        else:
            x_key = next(iter(scan_data))
        scan_x = scan_data[x_key]
        scan_y = scan_data.get("Y") if x_key == "X" else None
        x_label = data_dir / f"<{x_key} scan set>"
        y_label = data_dir / "<Y scan set>" if scan_y is not None else None
        return x_label, y_label, scan_x, scan_y
    raise FileNotFoundError("No spotfit data source specified. Provide paths.data_file or paths.offset_dir.")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_spotfit(config: FitConfig, args=None) -> Optional[FitResult]:
    stack = to_stack(config)

    data_file_x = resolve_config_path(config, config.data_file)
    data_file_y = resolve_config_path(config, config.data_file_y)
    if args:
        if not data_file_x:
            raw = getattr(args, "data_file", None)
            data_file_x = Path(raw) if raw else None
        if not data_file_y:
            raw = getattr(args, "data_file_y", None)
            data_file_y = Path(raw) if raw else None

    spot_guess = config.spot_size if config.spot_size is not None else (getattr(args, "spot_guess", 3.0) if args else 3.0)
    requested_freq = config.freq_spot
    if requested_freq is None and args:
        requested_freq = getattr(args, "freq", None)

    try:
        data_label_x, data_label_y, scan_x, scan_y = _load_spot_scans(config, data_file_x, data_file_y)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if requested_freq is not None:
        freq_idx = int(np.argmin(np.abs(scan_x.frequencies - requested_freq)))
        actual_freq = scan_x.frequencies[freq_idx]
        freq_label = f"{requested_freq} Hz, using harmonic: {actual_freq} Hz"
    else:
        freq_idx = len(scan_x.frequencies) - 1
        actual_freq = scan_x.frequencies[freq_idx]
        freq_label = f"{actual_freq} Hz (auto: highest)"

    sep_um = scan_x.offset
    amp_data_x = scan_x.r[:, freq_idx]
    print(f"Data file (X):      {data_label_x}")
    print(f"Requested freq:     {freq_label}")
    print(f"Offsets:            {len(sep_um)} points")

    target_x = _resolve_spot_target(config, axis="x" if scan_y is not None else None)
    fitter_x = FWHMFitter(stack=stack, freq=actual_freq, sep_um=sep_um)
    print("\nRunning spot-only fit (X)...")
    result_x = fitter_x.fit(amp_data_x, target_x)
    spot_x = _resolve_spot_value(result_x, spot_guess)

    spot_y = None
    result_y = None
    sep_um_y = None
    amp_data_y = None
    if scan_y is not None:
        freq_idx_y = int(np.argmin(np.abs(scan_y.frequencies - actual_freq)))
        sep_um_y = scan_y.offset
        amp_data_y = scan_y.r[:, freq_idx_y]
        print(f"Data file (Y):      {data_label_y}")
        print("Running spot-only fit (Y)...")
        target_y = _resolve_spot_target(config, axis="y")
        fitter_y = FWHMFitter(stack=stack, freq=scan_y.frequencies[freq_idx_y], sep_um=sep_um_y)
        result_y = fitter_y.fit(amp_data_y, target_y)
        spot_y = _resolve_spot_value(result_y, spot_guess)

    spot_avg = (spot_x + spot_y) / 2.0 if spot_y is not None else spot_x
    _print_spot_result(spot_x, spot_y, spot_avg, result_x, result_y)

    paths = resolve_fit_output_paths(config, args, command="spot")

    import matplotlib.pyplot as plt

    # --- Save X PNG + CSV --------------------------------------------------
    stack_x = result_x.fitted_stack if result_x.fitted_stack is not None else stack
    curve_x = calculate_spot_fit_curve(sep_um, amp_data_x, stack_x, spot_x, actual_freq)
    fig_x = plot_spot_fit(
        sep_um=sep_um, amp_data=amp_data_x, stack=stack_x,
        spot_size=spot_x, freq=actual_freq, result=result_x,
        direction=" (X)" if scan_y is not None else "", curve=curve_x,
    )
    x_plot_path = paths.next_plot_path("spot_X")
    fig_x.savefig(x_plot_path, dpi=150)
    plt.close(fig_x)
    print(f"Plot saved to {x_plot_path}")

    x_csv_path = paths.next_fit_csv_path("spot_X")
    write_spot_fit_csv(curve_x.x, curve_x.data, curve_x.model, x_csv_path)
    print(f"CSV saved to {x_csv_path}")

    # --- Save Y PNG + CSV --------------------------------------------------
    if scan_y is not None and result_y is not None and sep_um_y is not None and amp_data_y is not None:
        y_freq = scan_y.frequencies[int(np.argmin(np.abs(scan_y.frequencies - actual_freq)))]
        stack_y = result_y.fitted_stack if result_y.fitted_stack is not None else stack
        curve_y = calculate_spot_fit_curve(sep_um_y, amp_data_y, stack_y, spot_y, y_freq)
        fig_y = plot_spot_fit(
            sep_um=sep_um_y, amp_data=amp_data_y, stack=stack_y,
            spot_size=spot_y, freq=y_freq, result=result_y, direction=" (Y)", curve=curve_y,
        )
        y_plot_path = paths.next_plot_path("spot_Y")
        fig_y.savefig(y_plot_path, dpi=150)
        plt.close(fig_y)
        print(f"Plot saved to {y_plot_path}")

        y_csv_path = paths.next_fit_csv_path("spot_Y")
        write_spot_fit_csv(curve_y.x, curve_y.data, curve_y.model, y_csv_path)
        print(f"CSV saved to {y_csv_path}")

    # --- Save JSON ---------------------------------------------------------
    json_path = paths.next_fit_result_path()
    save_result(result_x, json_path)
    print(f"Result saved to {json_path}")

    if not result_x.success:
        handle_fit_exit(result_x.success)

    return result_x
