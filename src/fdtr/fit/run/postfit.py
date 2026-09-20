# src/fdtr/fit/run/postfit.py
"""Post-fit helpers shared across all fit runners.

Handles output path resolution, artifact writing, and exit-code logic
that was previously duplicated in each runner.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fdtr.output.paths import OutputPaths, derive_group_slug_from_config, resolve_output_dir, get_material_names


def resolve_fit_output_paths(config, args=None, command: str = "fit") -> OutputPaths:
    """Build an OutputPaths from config and optional CLI args.

    This is the identical 4-line block that was copy-pasted in every runner.
    """
    effective_output = config.output_dir
    config_path = Path(args.config) if args and hasattr(args, "config") and args.config else None
    out_dir = resolve_output_dir(
        effective_output,
        config_path=config_path,
        material_names=get_material_names(config),
    )
    return OutputPaths(base=out_dir, command=command, suffix=derive_group_slug_from_config(config_path))


def handle_fit_exit(success: bool) -> None:
    """Print warning and exit with code 2 if the fit did not converge."""
    if not success:
        print("WARNING: Optimiser did not converge.", file=sys.stderr)
        sys.exit(2)
