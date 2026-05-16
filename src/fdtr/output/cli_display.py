# src/fdtr/output/cli_display.py
"""CLI output formatting for FDTR fit results."""
from __future__ import annotations

from typing import Any


def print_result(result: Any) -> None:
    if _is_pipeline_result(result):
        _print_pipeline_result(result)
    else:
        _print_single_result(result)


def _is_pipeline_result(result) -> bool:
    return hasattr(result, "history") and hasattr(result, "final_values")


def _print_single_result(result) -> None:
    print("\n" + "=" * 50)
    print("  FDTR Fit Results")
    print("=" * 50)
    for name, value in result.fitted_values.items():
        if name.startswith("TBC"):
            print(f"  {name:20s} = {value:.4e} W/m^2K")
        elif name in ("spot_size", "spot_x", "spot_y"):
            print(f"  {name:20s} = {value:.4f} um")
        else:
            print(f"  {name:20s} = {value:.4f} W/mK")
    print("-" * 50)
    print(f"  {'Residual':20s} = {result.residual:.6e}")
    print(f"  {'Iterations':20s} = {result.nfev}")
    print(f"  {'Converged':20s} = {result.success}")
    print(f"  {'Message':20s} = {result.message}")
    print("=" * 50 + "\n")


def _print_pipeline_result(result) -> None:
    print("\n" + "=" * 50)
    print("  FDTR Pipeline Fit Results")
    print("=" * 50)
    for name, value in result.final_values.items():
        if name.startswith("TBC"):
            print(f"  {name:20s} = {value:.4e} W/m^2K")
        elif name in ("spot_size", "spot_x", "spot_y"):
            print(f"  {name:20s} = {value:.4f} um")
        else:
            print(f"  {name:20s} = {value:.4f} W/mK")
    print("-" * 50)
    if result.step_results and result.step_results[-1]:
        last_residual = result.step_results[-1][-1].residual
        print(f"  {'Final residual':20s} = {last_residual:.6e}")
    print(f"  {'Iterations':20s} = {result.n_iterations}")
    print(f"  {'Converged':20s} = {result.success}")
    print(f"  {'Message':20s} = {result.message}")
    print("=" * 50 + "\n")
