"""Data file validation and utility helpers for FDTR data loading."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np


def parse_ranges(ranges_str: str | None) -> list[tuple[float, float]] | None:
    """Parse semicolon-separated range pairs like ``'1e4,1e6;5e6,2e7'``.

    Returns ``None`` when *ranges_str* is ``None``.  Raises :class:`ValueError`
    on malformed input.
    """
    if ranges_str is None:
        return None
    ranges: list[tuple[float, float]] = []
    for pair in ranges_str.split(";"):
        parts = pair.strip().split(",")
        if len(parts) != 2:
            raise ValueError(f"Invalid range '{pair}'. Expected 'lo,hi'.")
        ranges.append((float(parts[0]), float(parts[1])))
    return ranges if ranges else None


def _is_valid_phase_file(filepath: str) -> bool:
    """Check if a file contains valid FDTR phase data.

    Valid phase data has >= 80% of points in the [-90, 0] degree range.
    """
    from fdtr.input.dataloader.freq_dataloader import load_freq_sweep

    try:
        sweep = load_freq_sweep(filepath)
    except Exception:
        return False
    if len(sweep.phase) == 0:
        return False
    in_range = np.sum((sweep.phase >= -90.0) & (sweep.phase <= 0.0))
    return bool((in_range / len(sweep.phase)) >= 0.8)


def _is_valid_offset_file(filepath: str) -> bool:
    """Check if a file contains valid offset scan data.

    Valid offset scan data has first-column values in the micrometer range
    (|offset| < 1000). Frequency-sweep data would have first-column values
    in the Hz range (> 1000).
    """
    from fdtr.input.dataloader.offset_dataloader import load_offset_scan

    try:
        scan = load_offset_scan(filepath)
    except Exception:
        return False
    if len(scan.offset) == 0:
        return False
    return bool(np.max(np.abs(scan.offset)) < 1000.0)


def _glob_case_insensitive(directory: Path, name_pattern: str, suffix: str) -> list:
    """Glob for files matching a name pattern (case-insensitive) with given suffix."""
    name_re = re.compile(name_pattern.replace("*", ".*"), re.IGNORECASE)
    matches = sorted(
        f for f in directory.glob(f"*{suffix}")
        if name_re.search(f.name)
    )
    return matches
