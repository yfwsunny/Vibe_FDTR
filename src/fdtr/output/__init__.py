"""Unified output package: paths, reports, and CLI formatting."""

from fdtr.output.paths import (
    OutputPaths,
    _auto_output_dir,
    _find_project_root,
    find_task_root,
    get_material_names,
    get_material_names_from_dict,
    resolve_task_root,
    resolve_output_dir,
)
from fdtr.output.report import ReportGenerator
from fdtr.output.summary import SummaryGenerator, organize_files

from fdtr.output import cli_display
from fdtr.output import result_io
from fdtr.output import plots
from fdtr.output import fit_plots
from fdtr.output import sensitivity_plots

__all__ = [
    "OutputPaths",
    "ReportGenerator",
    "SummaryGenerator",
    "cli_display",
    "find_task_root",
    "fit_plots",
    "get_material_names",
    "get_material_names_from_dict",
    "organize_files",
    "plots",
    "resolve_task_root",
    "resolve_output_dir",
    "result_io",
    "sensitivity_plots",
]
