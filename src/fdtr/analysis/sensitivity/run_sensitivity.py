"""Top-level orchestration for sensitivity analysis.

Provides :func:`run_sensitivity`, the public entry point called by the
CLI and other consumers.
"""
from __future__ import annotations

from pathlib import Path

from fdtr.analysis.sensitivity.engine import SensitivityResult, run_sensitivity_engine
from fdtr.analysis.sensitivity.prepare import prepare_sensitivity
from fdtr.input.config import FitConfig


def run_sensitivity(
    config: FitConfig,
    output_dir: Path | None = None,
) -> SensitivityResult:
    """Run a full sensitivity analysis.

    ``output_dir`` is accepted for backward-compatible call sites but artifact
    writing is handled by the CLI/output wrapper so naming policy stays
    centralized. Returns the :class:`SensitivityResult` regardless.
    """
    inputs = prepare_sensitivity(config)
    return run_sensitivity_engine(inputs, config)
