# src/fdtr/cli/fit.py
"""Config-driven fit entry point."""

from __future__ import annotations

import sys


def run_fit(args) -> None:
    """Execute the ``fit`` subcommand.

    Requires ``--config <toml>``.  Strategy is read from the TOML file.
    """
    from fdtr.input.config import from_toml
    from fdtr.fit.run import run_freqfit, run_offsetfit, run_spotfit, run_iterfit

    config_path = args.config

    config = from_toml(config_path)
    if getattr(args, "output_dir", None):
        config.output_dir = args.output_dir

    dispatch = {
        "freqfit": run_freqfit,
        "offsetfit": run_offsetfit,
        "spotfit": run_spotfit,
        "iterfit": run_iterfit,
    }
    handler = dispatch.get(config.strategy)
    if not handler:
        print(
            f"Error: Unknown strategy '{config.strategy}'.",
            file=sys.stderr,
        )
        sys.exit(1)
    handler(config, args=args)
