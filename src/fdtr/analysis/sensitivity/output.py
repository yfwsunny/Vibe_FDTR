"""Output handling for sensitivity analysis.

Lightweight wrapper that writes CSV and plot artifacts using the shared
``output`` package.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from fdtr.analysis.sensitivity.engine import SensitivityResult
from fdtr.output import OutputPaths
from fdtr.output.sensitivity_plots import plot_sensitivity_curves


# ---------------------------------------------------------------------------
# Artifacts type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityArtifacts:
    output_dir: Path
    csv_path: Path
    plot_path: Path


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------

def write_sensitivity_csv(result: SensitivityResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([result.axis_name, *result.parameter_names])
        for idx, axis_value in enumerate(result.axis_values):
            writer.writerow(
                [
                    f"{float(axis_value):.12g}",
                    *[
                        f"{float(result.curves[name][idx]):.12g}"
                        for name in result.parameter_names
                    ],
                ]
            )

    return path


# ---------------------------------------------------------------------------
# Unified output handler
# ---------------------------------------------------------------------------

def handle_sensitivity_output(
    result: SensitivityResult,
    output_dir: Path,
    suffix: str = "",
) -> SensitivityArtifacts:
    """Write CSV and plot artifacts, returning paths to all outputs."""
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    paths = OutputPaths(base=output_dir, command="freq")

    csv_path = write_sensitivity_csv(
        result, paths.next_sensitivity_csv_path(result.mode, result.signal, suffix)
    )

    fig = plot_sensitivity_curves(result)
    plot_path = paths.next_sensitivity_plot_path(result.mode, result.signal, suffix)
    try:
        fig.savefig(plot_path, dpi=150)
    finally:
        plt.close(fig)

    return SensitivityArtifacts(
        output_dir=output_dir,
        csv_path=csv_path,
        plot_path=plot_path,
    )
