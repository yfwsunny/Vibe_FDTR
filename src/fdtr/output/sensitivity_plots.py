"""Sensitivity-curve plotting for FDTR toolkit.

Migrated from ``analysis.sensitivity.sensitivity_plotting``.  Uses
``output.plots.create_figure`` for consistent styling.
"""
from __future__ import annotations

from matplotlib.figure import Figure

from fdtr.output.plots import create_figure


def plot_sensitivity_curves(result) -> Figure:
    """Plot sensitivity curves from a :class:`SensitivityResult`.

    Parameters
    ----------
    result : SensitivityResult
        Object with attributes ``axis_values``, ``curves`` (dict),
        ``parameter_names``, ``mode``, ``signal``.

    Returns
    -------
    Figure
    """
    fig, ax = create_figure()

    for name in result.parameter_names:
        ax.plot(result.axis_values, result.curves[name], linewidth=1.5, label=name)

    if result.mode == "freq":
        ax.set_xscale("log")
        ax.set_xlabel("Frequency (Hz)")
    else:
        ax.set_xlabel("Offset (um)")

    ax.set_ylabel("Relative sensitivity")
    ax.set_title(f"{result.mode} {result.signal} sensitivity")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.tight_layout()
    return fig
