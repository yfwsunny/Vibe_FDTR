# src/fdtr/fit/run/run_iterfit.py
"""Orchestration runner for iterative pipeline fitting."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

from fdtr.input.config import FitConfig, from_toml, to_stack, to_fit_targets
from fdtr.input.dataloader.pipeline_loader import load_pipeline_datasets
from fdtr.fit.iterfit import PipelineRunner, PipelineResult, resolve_pipeline_for_config
from fdtr.output.cli_display import print_result
from fdtr.output.result_io import save_result
from fdtr.model.layer import SYMMETRY_ISOTROPIC
from fdtr.output.fit_plots import write_freq_fit_csv, write_offset_fit_csv, write_spot_fit_csv
from fdtr.output.fit_curve_cal import (
    calculate_freq_fit_curve,
    calculate_offset_fit_curve,
    calculate_spot_fit_curve,
)
from fdtr.fit.offsetcenter_cal import center_amp_key_for_offset_data, resolve_center_amp
from fdtr.fit.run.postfit import resolve_fit_output_paths, handle_fit_exit
from fdtr.output.paths import OutputPaths
from fdtr.input.config.path_resolution import resolve_config_path
from fdtr.fit.iterfit.pipeline import is_builtin_pipeline_reference
from fdtr.common_types import SignalType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_final_stack(config: FitConfig, final_values: dict, spot_x: float):
    from fdtr.model.param import validate_targets, apply_params
    from fdtr.common_types import FitTarget
    final_stack = to_stack(config)
    non_spot_params = {k: v for k, v in final_values.items() if not k.startswith("spot")}
    if non_spot_params:
        dummy_targets = [
            FitTarget(name=k, initial_guess=v, bounds=(0.1, 10.0))
            for k, v in non_spot_params.items()
        ]
        resolved = validate_targets(dummy_targets, final_stack, allow_spot=False)
        final_stack, _ = apply_params(final_stack, spot_x, non_spot_params, resolved)
    return final_stack


def _extract_residuals(result: PipelineResult, pipeline, datasets: dict) -> dict[str, float]:
    last_iter_results = result.step_results[-1]
    residuals: dict[str, float] = {}
    ri = 0
    for step in pipeline.steps:
        if step.data_key and step.data_key not in datasets:
            continue
        if ri < len(last_iter_results):
            residuals[step.name] = last_iter_results[ri].residual
        ri += 1
    return residuals


def _first_step(pipeline, *, fitter: str, data_key: str):
    """Return the first pipeline step matching a fitter/data-key pair."""
    return next(
        (step for step in pipeline.steps if step.fitter == fitter and step.data_key == data_key),
        None,
    )


def _fitted_values_for_step(final_values: dict, step) -> dict:
    """Select final fitted values using the target names declared by a step."""
    if step is None:
        return {}
    return {
        name: final_values[name]
        for name in step.target_names
        if name in final_values
    }


def _residual_for_step(residuals: dict[str, float], pipeline, step, fitter: str) -> float:
    """Return a step residual, falling back to the first residual for a fitter."""
    if step is not None:
        return residuals.get(step.name, 0.0)
    return next(
        (residuals.get(candidate.name, 0.0) for candidate in pipeline.steps if candidate.fitter == fitter),
        0.0,
    )


def _print_iter_result(result: PipelineResult) -> None:
    fv = result.final_values
    spot_x = fv.get("spot_x", fv.get("spot_size", 0))
    spot_y = fv.get("spot_y", spot_x)
    spot_size = fv.get("spot_size", (spot_x + spot_y) / 2.0)
    print("\n" + "=" * 50)
    print("  FDTR Iterative Combined Fit Results")
    print("=" * 50)
    print(f"  {'spot_x':20s} = {spot_x:.4f} um")
    print(f"  {'spot_y':20s} = {spot_y:.4f} um")
    print(f"  {'spot_size':20s} = {spot_size:.4f} um")
    for name, value in fv.items():
        if name.startswith("spot"):
            continue
        if name.startswith("TBC_"):
            print(f"  {name:20s} = {value:.4e} W/m^2K")
        elif name.startswith(("S_", "Sr_", "Sz_")):
            print(f"  {name:20s} = {value:.4f} W/mK")
    print("-" * 50)
    print(f"  {'Iterations':20s} = {result.n_iterations}")
    print(f"  {'Converged':20s} = {result.success}")
    print("=" * 50 + "\n")


def _plot_and_save_iter_results(
    config: FitConfig,
    result: PipelineResult,
    pipeline,
    datasets: dict,
    paths: OutputPaths,
) -> list[Path]:
    """Generate and save iterfit diagnostic plots + CSV. Returns plot paths."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fdtr.output.fit_plots import plot_freq_fit, plot_offset_fit, plot_spot_fit
    from fdtr.common_types import FitResult

    fv = result.final_values
    spot_x = fv.get("spot_x", fv.get("spot_size", 0))
    spot_y = fv.get("spot_y", spot_x)
    spot_size = fv.get("spot_size", (spot_x + spot_y) / 2.0)
    residuals = _extract_residuals(result, pipeline, datasets)
    final_stack = _build_final_stack(config, fv, spot_x)
    display_stack = final_stack if hasattr(final_stack, "substrate_index") else to_stack(config)
    substrate_idx = display_stack.substrate_index
    substrate = display_stack.layers[substrate_idx]
    config.spot_size = spot_size

    plot_paths: list[Path] = []
    _MAX_PLOT_PTS: int | None = None

    # --- Spot fit plot (X) -------------------------------------------------
    if "offset_x_amplitude" in datasets:
        sep_um, amp_data = datasets["offset_x_amplitude"]
        sr = FitResult(
            fitted_values={"spot_x": spot_x},
            residual=residuals.get("spot_x", 0.0),
            success=True, nfev=0,
            fitted_stack=final_stack,
        )
        curve = calculate_spot_fit_curve(
            sep_um, amp_data, final_stack, spot_x, config.freq_spot, max_points=_MAX_PLOT_PTS
        )
        fig = plot_spot_fit(sep_um, amp_data, final_stack, spot_x, config.freq_spot,
                            sr, direction=" (X)", max_points=_MAX_PLOT_PTS, curve=curve)
        p = paths.next_plot_path("spot_X")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        plot_paths.append(p)

        csv_path = paths.next_fit_csv_path("spot_X")
        write_spot_fit_csv(curve.x, curve.data, curve.model, csv_path)

    # --- Spot fit plot (Y) -------------------------------------------------
    if "offset_y_amplitude" in datasets:
        sep_um_y, amp_data_y = datasets["offset_y_amplitude"]
        sr_y = FitResult(
            fitted_values={"spot_y": spot_y},
            residual=residuals.get("spot_y", 0.0),
            success=True, nfev=0,
            fitted_stack=final_stack,
        )
        curve_y = calculate_spot_fit_curve(
            sep_um_y, amp_data_y, final_stack, spot_y, config.freq_spot, max_points=_MAX_PLOT_PTS
        )
        fig = plot_spot_fit(sep_um_y, amp_data_y, final_stack, spot_y, config.freq_spot,
                            sr_y, direction=" (Y)", max_points=_MAX_PLOT_PTS, curve=curve_y)
        p = paths.next_plot_path("spot_Y")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        plot_paths.append(p)

        csv_path = paths.next_fit_csv_path("spot_Y")
        write_spot_fit_csv(curve_y.x, curve_y.data, curve_y.model, csv_path)

    # --- Offset phase fit plot ---------------------------------------------
    if "offset_x_phase" in datasets:
        offset_step = _first_step(pipeline, fitter="offset", data_key="offset_x_phase")
        phase_sep_sub, phase_offset_sub = datasets["offset_x_phase"]
        center_amp_data = phase_offset_sub
        center_amp_key = center_amp_key_for_offset_data("offset_x_phase")
        if center_amp_key and center_amp_key in datasets:
            center_offset_data, raw_center_amp = datasets[center_amp_key]
            center_amp_data = resolve_center_amp(
                phase_sep_sub,
                phase_offset_sub,
                center_offset_data=center_offset_data,
                center_amp_data=raw_center_amp,
            )
        offset_fitted_values = _fitted_values_for_step(fv, offset_step)
        if not offset_fitted_values:
            offset_key = f"S_{substrate_idx}" if substrate.symmetry == SYMMETRY_ISOTROPIC else f"Sr_{substrate_idx}"
            offset_fitted_values = {offset_key: substrate.Sr}
        offset_freq = (
            offset_step.freq_offset
            if offset_step is not None and offset_step.freq_offset is not None
            else config.freq_offset
        )
        sr_off = FitResult(
            fitted_values=offset_fitted_values,
            residual=_residual_for_step(residuals, pipeline, offset_step, "offset"),
            success=True, nfev=0,
            fitted_stack=final_stack,
        )
        config.spot_size = spot_x
        curve = calculate_offset_fit_curve(
            phase_sep_sub,
            phase_offset_sub,
            offset_freq,
            config,
            sr_off,
            max_points=_MAX_PLOT_PTS,
            center_amp_data=center_amp_data,
        )
        fig = plot_offset_fit(phase_sep_sub, phase_offset_sub, offset_freq,
                              config, sr_off, max_points=_MAX_PLOT_PTS, curve=curve,
                              center_amp_data=center_amp_data)
        config.spot_size = spot_size
        p = paths.next_plot_path("offset_phase")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        plot_paths.append(p)

        csv_path = paths.next_fit_csv_path("offset_phase")
        write_offset_fit_csv(curve.x, curve.data, curve.model, csv_path, signal_name="phase")

    # --- Phase sweep fit plot ----------------------------------------------
    if "freq_phase" in datasets:
        freq_step = _first_step(pipeline, fitter="freq", data_key="freq_phase")
        freq_sweep, phase_sweep = datasets["freq_phase"]
        freq_fitted_values = _fitted_values_for_step(fv, freq_step)
        if not freq_fitted_values:
            sz_val = substrate.Sz
            tbc_val = next((v for k, v in fv.items() if k.startswith("TBC_")), 0)
            tbc_key = next((k for k in fv if k.startswith("TBC_")), "TBC_1")
            substrate_key = f"S_{substrate_idx}" if substrate.symmetry == SYMMETRY_ISOTROPIC else f"Sz_{substrate_idx}"
            freq_fitted_values = {substrate_key: sz_val, tbc_key: tbc_val}
        sr_freq = FitResult(
            fitted_values=freq_fitted_values,
            residual=_residual_for_step(residuals, pipeline, freq_step, "freq"),
            success=True, nfev=0,
            fitted_stack=final_stack,
        )
        curve = calculate_freq_fit_curve(freq_sweep, phase_sweep, config, sr_freq, max_points=_MAX_PLOT_PTS)
        fig = plot_freq_fit(freq_sweep, phase_sweep, config, sr_freq, max_points=_MAX_PLOT_PTS, curve=curve)
        p = paths.next_plot_path("freq_sweep")
        fig.savefig(p, dpi=150)
        plt.close(fig)
        plot_paths.append(p)

        csv_path = paths.next_fit_csv_path("freq_sweep")
        write_freq_fit_csv(curve.x, curve.data, curve.model, csv_path, signal_name="phase")

    return plot_paths


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_iterfit(config: FitConfig, args=None):
    """Execute iterative pipeline fitting: config -> load data -> pipeline run -> output."""
    if config.pipeline and not is_builtin_pipeline_reference(config.pipeline):
        pipeline_path = resolve_config_path(config, config.pipeline)
        print(f"Loading custom pipeline from: {pipeline_path}")
    pipeline = resolve_pipeline_for_config(config)

    iterations = config.iterations
    print(f"\nRunning iterative fit ({iterations} iterations)...")

    datasets = load_pipeline_datasets(config, pipeline)

    runner = PipelineRunner(pipeline, config, datasets)
    result = runner.run(n_iterations=iterations)

    _print_iter_result(result)

    paths = resolve_fit_output_paths(config, args, command="iter")

    # --- Plot + CSV --------------------------------------------------------
    plot_paths = _plot_and_save_iter_results(config, result, pipeline, datasets, paths)
    if plot_paths:
        print(f"  Saved {len(plot_paths)} fit plots to {paths.base}")

    # --- Save JSON ---------------------------------------------------------
    json_path = paths.next_fit_result_path()
    save_result(result, json_path)
    print(f"Result saved to {json_path}")

    if not result.success:
        print("WARNING: Not all sub-fits converged.", file=sys.stderr)

    return result
