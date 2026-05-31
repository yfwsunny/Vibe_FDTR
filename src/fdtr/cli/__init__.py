# src/fdtr/cli/__init__.py
"""FDTR Toolkit command-line interface.

CLI built on argparse.  Provides subcommands for FDTR data fitting:

- ``fit``           — run fitting via TOML config (``--config``)
- ``init-config``   — generate template TOML config


Usage::

    fdtr fit --config config.toml

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from fdtr.cli.fit import run_fit
from fdtr.cli.sensitivity import run_sensitivity
from fdtr.cli.uncertainty import run_uncertainty
from fdtr.cli.initconfig import run_init_config
from fdtr.cli.materials_cmd import run_list_materials, run_show_material
from fdtr.cli.summary import run_summary


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="fdtr",
        description="FDTR Toolkit – Frequency Domain Thermoreflectance data processing",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # --- fit subcommand (config-only) ---
    uf = subparsers.add_parser(
        "fit",
        description="Run fitting from a TOML config file.",
        help="Run fitting from config",
        allow_abbrev=False,
    )
    uf.add_argument(
        "--config",
        type=str,
        required=True,
        metavar="PATH",
        help="Path to TOML config file (required).",
    )

    # --- sensitivity subcommand ---
    sens = subparsers.add_parser(
        "sensitivity",
        description="Run model-based FDTR sensitivity analysis from a TOML config.",
        help="Sensitivity analysis from config",
        allow_abbrev=False,
    )
    sens.add_argument(
        "--config",
        type=str,
        required=True,
        metavar="PATH",
        help="Path to TOML config file (required).",
    )

    # --- uncertainty subcommand ---
    unc = subparsers.add_parser(
        "uncertainty",
        description="Calculate parameter uncertainties for FDTR measurements.",
        help="Uncertainty calculation (post-fit or independent mode)",
        allow_abbrev=False,
    )
    unc.add_argument(
        "--config", "-c",
        type=str,
        metavar="PATH",
        help="Path to TOML config file (independent mode)",
    )
    unc.add_argument(
        "--fit-result", "-f",
        type=str,
        metavar="PATH",
        help="Path to fit result JSON file (post-fit mode)",
    )
    unc.add_argument(
        "--full-output",
        action="store_true",
        default=None,
        help="Include full output (covariance matrix, contributions)",
    )

    # --- init-config subcommand ---
    ic = subparsers.add_parser(
        "init-config",
        description="Generate a template TOML configuration file.",
        help="Generate template config file",
    )
    from fdtr.cli.initconfig_args import add_init_config_args
    add_init_config_args(ic)

    # --- scan-data subcommand ---
    sd = subparsers.add_parser(
        "scan-data",
        description="Scan a directory for FDTR data files and output structured JSON.",
        help="Scan data directory",
    )
    sd.add_argument("dir", type=str, help="Data directory to scan")
    sd.add_argument("--offset-x-glob", type=str, default=None)
    sd.add_argument("--offset-y-glob", type=str, default=None)
    sd.add_argument("--freq-image-glob", type=str, default=None)
    sd.add_argument("--temp-regex", type=str, default=None)
    sd.add_argument("--group", type=str, default=None, help="Return detail for one group_key only")
    sd.add_argument(
        "--save",
        action="store_true",
        default=False,
        help="Save scan-data JSON under tasks/ instead of printing only to stdout",
    )
    sd.add_argument(
        "--save-all",
        action="store_true",
        default=False,
        help="Save per-group JSON for every discovered group plus a summary index",
    )
    sd.add_argument(
        "--detail-threshold",
        type=int,
        default=4,
        help="Return only group_key indexes when the discovered group count exceeds this threshold",
    )

    # --- list-materials subcommand ---
    lm = subparsers.add_parser(
        "list-materials",
        description="List all available materials in the library.",
        help="List available materials",
    )

    # --- show-material subcommand ---
    sm = subparsers.add_parser(
        "show-material",
        description="Show material properties at a given temperature.",
        help="Show material properties",
    )
    sm.add_argument(
        "name",
        type=str,
        help="Material name (e.g. Gold, Graphite)",
    )
    sm.add_argument(
        "-T", "--temperature",
        type=float,
        default=296.0,
        help="Temperature in Kelvin (default: 296.0)",
    )

    # --- summary subcommand ---
    smr = subparsers.add_parser(
        "summary",
        description="Generate a cross-analysis summary report from task directory artifacts.",
        help="Generate summary report",
    )
    smr.add_argument(
        "task_dir",
        type=str,
        help="Task directory containing FDTR output artifacts",
    )
    smr.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for summary Markdown (default: auto-named in task dir)",
    )
    smr.add_argument(
        "--organize",
        action="store_true",
        default=False,
        help="Archive files into inputs/ and results/ subdirectories before generating report",
    )

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI entry point. Parses args and dispatches to the appropriate subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "fit": run_fit,
        "sensitivity": run_sensitivity,
        "uncertainty": run_uncertainty,
        "init-config": run_init_config,
        "list-materials": run_list_materials,
        "show-material": run_show_material,
        "scan-data": _run_scan_data,
        "summary": run_summary,
    }
    handler = dispatch.get(args.subcommand)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    handler(args)


def _run_scan_data(args) -> None:
    """Scan a data directory and print JSON summary."""
    from fdtr.input.dataloader.scanner import scan_data_directory
    from fdtr.output import resolve_task_root

    result = scan_data_directory(
        args.dir,
        offset_x_glob=args.offset_x_glob,
        offset_y_glob=args.offset_y_glob,
        freq_image_glob=args.freq_image_glob,
        temp_regex=args.temp_regex,
        group=args.group,
        detail_threshold=args.detail_threshold,
    )
    payload = json.dumps(result, indent=2, ensure_ascii=False)

    if args.save_all and not args.group:
        full_result = scan_data_directory(
            args.dir,
            offset_x_glob=args.offset_x_glob,
            offset_y_glob=args.offset_y_glob,
            freq_image_glob=args.freq_image_glob,
            temp_regex=args.temp_regex,
            detail_threshold=args.detail_threshold,
            force_full_detail=True,
        )
        task_root = resolve_task_root(group_key=Path(args.dir).name)
        saved = 0
        for group_detail in full_result.get("groups", []):
            gk = group_detail.get("group_key")
            if not gk:
                continue
            path = task_root / f"scan_group_{gk}.json"
            path.write_text(
                json.dumps(group_detail, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            saved += 1
        index_path = task_root / "scan_data_index.json"
        index_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved {saved} group scans + index to {task_root}")
        return

    if args.save:
        group_key = result.get("group_key") or args.group or Path(args.dir).name
        task_root = resolve_task_root(group_key=group_key)
        file_name = (
            f"scan_group_{result['group_key']}.json"
            if result.get("group_key")
            else "scan_data.json"
        )
        output_path = task_root / file_name
        output_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Scan data written to {output_path}")
        return

    print(payload)
