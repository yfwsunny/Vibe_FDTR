# src/fdtr/fit/run/run_freqfit.py
"""Orchestration runner for freq-sweep fitting."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

from fdtr.input.config import FitConfig, from_toml, to_stack, to_fit_targets
from fdtr.common_types import SignalType
from fdtr.fit.freq_fitter import FreqFitter
from fdtr.input.dataloader.cli_data_loader import _load_freq_sweep_data
from fdtr.output.cli_display import print_result
from fdtr.output.fit_plots import plot_freq_fit, write_freq_fit_csv
from fdtr.output.fit_curve_cal import calculate_freq_fit_curve
from fdtr.output.result_io import save_result
from fdtr.fit.run.postfit import resolve_fit_output_paths, handle_fit_exit
from fdtr.input.config.path_resolution import resolve_config_path
from fdtr.input.config.prepare_spot import (
    ignored_directional_spot_warning,
    require_scalar_spot_size,
)


def run_freqfit(config: FitConfig, args=None) -> None:
    """Execute freq-sweep fitting: config -> load data -> fit -> output."""
    signal = SignalType.PHASE if config.signal == "phase" else SignalType.AMPLITUDE
    spot_size_um = require_scalar_spot_size(config, "freqfit")
    config.spot_size = spot_size_um
    spot_warning = ignored_directional_spot_warning(config, "freqfit")
    if spot_warning:
        print(f"Warning: {spot_warning}", file=sys.stderr)
    stack = to_stack(config)
    targets = to_fit_targets(config)

    # Resolve freq_ranges
    freq_ranges = config.freq_ranges

    # --- Load data --------------------------------------------------------
    data_path = resolve_config_path(config, config.phase_dir or config.data_file)
    if data_path is None:
        print("Error: No phase_dir or data_file specified for freq fitting.", file=sys.stderr)
        sys.exit(1)
    if not data_path.exists():
        print(f"Error: Data source does not exist: {data_path}", file=sys.stderr)
        sys.exit(1)

    use_average = config.average
    n_points = config.phase_points
    print(f"Loading data from:  {data_path} (average={use_average}, n={n_points})")
    freq_data, phase_data, amp_data = _load_freq_sweep_data(
        data_path, average=use_average, n_points=n_points,
        pattern=config.phase_pattern, explicit_files=config.phase_files,
    )
    print(f"Data points:        {len(freq_data)}")

    if signal == SignalType.PHASE:
        signal_data = phase_data
    else:
        if amp_data is None:
            print("Error: Amplitude data not available for amplitude-mode fitting.", file=sys.stderr)
            sys.exit(1)
        signal_data = amp_data

    # Default freq range from config or fallback
    if not freq_ranges:
        freq_ranges = [(5e4, 2e7)]
        print("Warning: freq_ranges not set in config, using default [5e4, 2e7] Hz.", file=sys.stderr)

    # --- Run fit ----------------------------------------------------------
    fitter = FreqFitter(
        stack=stack,
        signal=signal,
        spot_size_um=spot_size_um,
        freq_ranges=freq_ranges,
        n_points=n_points,
    )

    print(f"\nRunning freq-sweep fit (signal={signal.value})...")
    result = fitter.fit(freq_data, signal_data, targets)
    print_result(result)

    # --- Resolve output directory -----------------------------------------
    paths = resolve_fit_output_paths(config, args, command="freq")

    # --- Compute shared plot/CSV curve ------------------------------------
    curve = None
    if result.fitted_stack is not None:
        curve = calculate_freq_fit_curve(freq_data, signal_data, config, result)
        if signal == SignalType.PHASE:
            plot_name = "phase_sweep"
            csv_name = "phase"
        else:
            plot_name = "amplitude_sweep"
            csv_name = "amplitude"
    else:
        plot_name = "phase_sweep" if signal == SignalType.PHASE else "amplitude_sweep"
        csv_name = "phase" if signal == SignalType.PHASE else "amplitude"

    # --- Save PNG ----------------------------------------------------------
    fig = plot_freq_fit(freq_data, signal_data, config, result, curve=curve)
    plot_path = paths.next_plot_path(plot_name)
    fig.savefig(plot_path, dpi=150)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"Plot saved to {plot_path}")

    # --- Save CSV ----------------------------------------------------------
    csv_path = paths.next_fit_csv_path(csv_name)
    if curve is None:
        curve = calculate_freq_fit_curve(freq_data, signal_data, config, result)
    write_freq_fit_csv(curve.x, curve.data, curve.model, csv_path, signal_name=csv_name)
    print(f"CSV saved to {csv_path}")

    # --- Save JSON ---------------------------------------------------------
    json_path = paths.next_fit_result_path()
    save_result(result, json_path)
    print(f"Result saved to {json_path}")

    if not result.success:
        handle_fit_exit(result.success)
