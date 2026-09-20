"""CLI command for sensitivity analysis — thin dispatcher."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def _is_flat_analysis_config(path: Path) -> bool:
    """Return True if the TOML has a top-level ``base_config`` key."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return "base_config" in data


def _load_config(path: Path):
    """Load a FitConfig, auto-detecting flat analysis vs legacy format."""
    if _is_flat_analysis_config(path):
        from fdtr.input.config.analysis_config import load_analysis_config
        return load_analysis_config(path, "sensitivity")
    from fdtr.input.config import from_toml
    return from_toml(path)


def run_sensitivity(args) -> None:
    """Dispatch sensitivity analysis to the engine module."""
    from fdtr.input.config import SensitivitySpec
    from fdtr.analysis.sensitivity.run_sensitivity import run_sensitivity as run_engine
    from fdtr.analysis.sensitivity.output import handle_sensitivity_output
    from fdtr.output import resolve_output_dir, get_material_names
    from fdtr.output.paths import derive_group_slug_from_config

    if not getattr(args, "config", None):
        print("Error: --config is required for the 'sensitivity' subcommand.", file=sys.stderr)
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config(config_path)
    sensitivity = config.sensitivity or SensitivitySpec()

    # Unified path resolution: [sensitivity] output_dir > [paths] output_dir.
    effective_output = (
        (config.sensitivity.output_dir if config.sensitivity else None)
        or config.output_dir
    )
    out_dir = resolve_output_dir(
        effective_output,
        config_path=config_path,
        material_names=get_material_names(config),
    )

    result = run_engine(config, output_dir=out_dir)
    artifacts = handle_sensitivity_output(
        result,
        output_dir=out_dir,
        suffix=derive_group_slug_from_config(config_path),
    )

    print(f"\nSensitivity analysis complete — {result.mode} {result.signal}")
    print(f"Output directory: {out_dir}")
