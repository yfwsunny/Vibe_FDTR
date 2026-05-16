"""Top-level orchestration for uncertainty analysis.

Provides the public ``run_uncertainty`` entry point that wires together
preparation, engine, and output.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from fdtr.analysis.uncertainty.engine import (
    UncertaintyResult,
    run_uncertainty_engine,
)
from fdtr.analysis.uncertainty.output import handle_uncertainty_output
from fdtr.analysis.uncertainty.prepare import prepare_uncertainty


def run_uncertainty(
    config,
    x_data: Optional[np.ndarray] = None,
    output_path: Optional[str] = None,
) -> UncertaintyResult:
    """Run uncertainty calculation.

    Args:
        config: Full config dictionary or FitConfig object.
        x_data: Optional experimental x data (for post-fit mode).
            If None, generated from config.
        output_path: If provided, save JSON result to this path.

    Returns:
        UncertaintyResult object.
    """
    inputs = prepare_uncertainty(config, x_data=x_data)

    # Extract the FitConfig for the engine
    from fdtr.input.config.config_io import _from_dict

    if isinstance(config, dict):
        fit_config = _from_dict(config)
    else:
        fit_config = config

    result = run_uncertainty_engine(inputs, fit_config)

    if output_path:
        handle_uncertainty_output(result, config, output_path)

    return result
