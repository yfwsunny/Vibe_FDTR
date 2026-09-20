# src/fdtr/output/plots.py
"""Shared plotting infrastructure for FDTR toolkit."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure


def setup_matplotlib(backend: str = "Agg") -> None:
    """Set matplotlib backend."""
    matplotlib.use(backend)


def create_figure(figsize: tuple[float, float] = (8, 5)) -> tuple[Figure, plt.Axes]:
    """Create a styled figure and axes."""
    fig, ax = plt.subplots(figsize=figsize)
    ax.grid(True, which="major", linestyle="-", alpha=0.3)
    ax.grid(True, which="minor", linestyle=":", alpha=0.2)
    return fig, ax


def save_or_show(
    fig: Figure,
    path: Optional[Path] = None,
    *,
    dpi: int = 150,
    show: bool = False,
) -> Optional[Path]:
    """Save figure to path or display. Returns save path if saved."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=dpi)
        plt.close(fig)
        return path
    if show:
        plt.show()
    else:
        plt.close(fig)
    return None
