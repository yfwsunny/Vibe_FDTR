# src/fdtr/cli/summary.py
"""CLI dispatcher for the summary subcommand."""
from __future__ import annotations

from pathlib import Path

from fdtr.output.summary import SummaryGenerator, organize_files
from fdtr.output.paths import OutputPaths, derive_group_slug_from_artifact


def run_summary(args) -> None:
    """Generate a cross-analysis summary report for a task directory."""
    task_dir = Path(args.task_dir).resolve()
    if not task_dir.is_dir():
        print(f"Error: {task_dir} is not a directory", file=__import__("sys").stderr)
        __import__("sys").exit(1)

    if args.organize:
        organize_files(task_dir)
        print(f"Files organized into {task_dir / 'inputs'} and {task_dir / 'results'}")

    gen = SummaryGenerator(task_dir)
    artifacts = gen.scan()

    if not artifacts.fit_results and not artifacts.sensitivity_csvs and not artifacts.uncertainty_results:
        print(f"No FDTR artifacts found in {task_dir}", file=__import__("sys").stderr)
        __import__("sys").exit(1)

    # Determine suffix from existing artifacts
    suffix = ""
    if artifacts.fit_results:
        suffix = derive_group_slug_from_artifact(artifacts.fit_results[0])
    elif artifacts.configs:
        suffix = derive_group_slug_from_artifact(artifacts.configs[0])

    paths = OutputPaths(base=task_dir, command="summary", suffix=suffix)

    output = Path(args.output) if args.output else paths.next_summary_path(suffix)
    saved = gen.save(output)
    print(f"Summary saved to {saved}")
