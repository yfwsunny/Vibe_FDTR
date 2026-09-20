"""Result formatting and output utilities for uncertainty analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from fdtr.analysis.uncertainty.engine import UncertaintyResult


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder for numpy types."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        return super().default(obj)


def format_result(result: UncertaintyResult) -> str:
    """Format result as human-readable string."""
    lines = ["Uncertainty Calculation Result", "=" * 40, ""]

    lines.append("Target Parameters Relative Uncertainty:")
    for param, uncert in result.relative_uncertainties.items():
        lines.append(f"  {param:<15} {uncert * 100:>6.2f}%")

    if result.parameter_contributions:
        lines.append("\nParameter Contribution Breakdown (% of total variance):")
        for target, contribs in result.parameter_contributions.items():
            lines.append(f"\n  {target}:")
            sorted_contribs = sorted(contribs.items(), key=lambda x: x[1], reverse=True)
            for known, contrib in sorted_contribs:
                lines.append(f"    {known:<15} {contrib:>6.2f}%")

    return "\n".join(lines)


def save_result(
    result: UncertaintyResult,
    filepath: str,
    include_full: bool = False,
):
    """Save result to JSON file.

    Args:
        result: UncertaintyResult object
        filepath: Output file path
        include_full: Whether to include full data (covariance matrix, Jacobians)
    """
    data = {
        "target_params": result.target_params,
        "relative_uncertainties": result.relative_uncertainties,
        "known_params": result.known_params,
    }

    if include_full and result.parameter_contributions:
        data["parameter_contributions"] = result.parameter_contributions
    if include_full and result.covariance_matrix is not None:
        data["covariance_matrix"] = result.covariance_matrix

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, cls=NumpyEncoder)


def handle_uncertainty_output(
    result: UncertaintyResult,
    config,
    output_path: Optional[str] = None,
) -> None:
    """Unified output: print formatted result and optionally save to file.

    Args:
        result: UncertaintyResult to display/save.
        config: Config dict (used to determine full_output flag).
        output_path: If provided, save JSON result here.
    """
    print(format_result(result))

    if output_path:
        include_full = False
        if isinstance(config, dict):
            include_full = config.get("uncertainty", {}).get("full_output", False)
        save_result(result, output_path, include_full=include_full)
        print(f"\nResult saved to {output_path}")
