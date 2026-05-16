# src/fdtr/fit/run/run_offsetfit.py
"""Orchestration runner for beam-offset fitting."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

from fdtr.input.config import FitConfig, from_toml, to_stack, to_fit_targets
from fdtr.common_types import SignalType
from fdtr.fit.offset_fitter import OffsetFitter
from fdtr.input.dataloader.cli_data_loader import _load_offset_scan_data
from fdtr.input.dataloader.offset_dataloader import load_offset_scan
from fdtr.output.cli_display import print_result
from fdtr.output.fit_plots import plot_offset_fit, write_offset_fit_csv
from fdtr.output.fit_curve_cal import calculate_offset_fit_curve
from fdtr.output.result_io import save_result
from fdtr.fit.run.postfit import resolve_fit_output_paths, handle_fit_exit
from fdtr.input.config.path_resolution import resolve_config_path


def run_offsetfit(config: FitConfig, args=None) -> None:
    """Execute beam-offset fitting: config -> load data -> fit -> output."""
    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE
    stack = to_stack(config)
    targets = to_fit_targets(config)

    # --- Load data --------------------------------------------------------
    if config.offset_dir:
        data_dir = resolve_config_path(config, config.offset_dir)
        if not data_dir.is_dir():
            print(f"Error: Offset directory does not exist: {data_dir}", file=sys.stderr)
            sys.exit(1)

        use_average = config.average
        n_points = config.offset_points
        print(f"Loading offset scans from: {data_dir} (average={use_average}, n={n_points})")

        scan_data = _load_offset_scan_data(
            data_dir,
            average=use_average,
            n_points=n_points,
            pattern=config.offset_pattern,
            explicit_files=config.offset_files,
        )
        if "X" in scan_data:
            direction = "X"
        elif "Y" in scan_data:
            direction = "Y"
        else:
            direction = list(scan_data.keys())[0]
        scan = scan_data[direction]
    elif config.data_file:
        data_path = resolve_config_path(config, config.data_file)
        if not data_path.is_file():
            print(f"Error: Data file does not exist: {data_path}", file=sys.stderr)
            sys.exit(1)
        scan = load_offset_scan(str(data_path))
    else:
        print("Error: No data source specified. Provide offset_dir or data_file.", file=sys.stderr)
        sys.exit(1)

    # --- Resolve frequency ------------------------------------------------
    freq = config.freq_offset
    if freq is None:
        print("Error: --freq / freq_offset is required for offset fitting.", file=sys.stderr)
        print("Available frequencies from data:", file=sys.stderr)
        for i, f in enumerate(scan.frequencies):
            label = " (highest)" if i == len(scan.frequencies) - 1 else ""
            print(f"  Harmonic {i+1}: {f:.4e} Hz{label}", file=sys.stderr)
        sys.exit(1)

    freq_idx = int(np.argmin(np.abs(scan.frequencies - freq)))
    actual_freq = scan.frequencies[freq_idx]
    sep_um = scan.offset

    if signal == SignalType.PHASE:
        signal_data = scan.theta[:, freq_idx]
    else:
        signal_data = scan.r[:, freq_idx]

    sr_guess = next((t.initial_guess * t.scale for t in targets if "Sr" in t.name), None)
    print(f"Data source:         {config.offset_dir or config.data_file}")
    print(f"Requested freq:      {freq} Hz, using harmonic: {actual_freq} Hz")
    print(f"Spot size:           {config.spot_size} um")
    if sr_guess is not None:
        print(f"Sr initial guess:   {sr_guess} W/mK")
    print(f"Signal:              {signal.value}")

    offset_ranges = config.offset_ranges
    if not offset_ranges:
        offset_ranges = [(-15.0, 15.0)]
        print("Warning: offset_ranges not set in config, using default [-15, 15] um.", file=sys.stderr)

    # --- Run fit ----------------------------------------------------------
    fitter = OffsetFitter(
        stack=stack,
        signal=signal,
        freq=actual_freq,
        spot_size_um=config.spot_size,
        offset_ranges=offset_ranges,
        n_points=config.offset_points,
    )

    print(f"\nRunning offset fit (signal={signal.value})...")
    result = fitter.fit(sep_um, signal_data, targets)
    print_result(result)

    # --- Resolve output directory -----------------------------------------
    paths = resolve_fit_output_paths(config, args, command="offset")

    # --- Compute shared plot/CSV curve ------------------------------------
    curve = calculate_offset_fit_curve(sep_um, signal_data, actual_freq, config, result)
    if signal == SignalType.PHASE:
        plot_name = "offset_phase"
        csv_name = "phase"
    else:
        plot_name = "offset_amplitude"
        csv_name = "amplitude"

    # --- Save PNG ----------------------------------------------------------
    fig = plot_offset_fit(sep_um, signal_data, actual_freq, config, result, curve=curve)
    plot_path = paths.next_plot_path(plot_name)
    fig.savefig(plot_path, dpi=150)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"Plot saved to {plot_path}")

    # --- Save CSV ----------------------------------------------------------
    csv_path = paths.next_fit_csv_path(plot_name)
    write_offset_fit_csv(curve.x, curve.data, curve.model, csv_path, signal_name=csv_name)
    print(f"CSV saved to {csv_path}")

    # --- Save JSON ---------------------------------------------------------
    json_path = paths.next_fit_result_path()
    save_result(result, json_path)
    print(f"Result saved to {json_path}")

    if not result.success:
        handle_fit_exit(result.success)
