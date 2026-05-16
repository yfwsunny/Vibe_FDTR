"""Shared TOML formatting and range-parsing utilities."""

from __future__ import annotations

import json


def fmt(value: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"Unsupported TOML value type: {type(value)}")


def fmt_list(items: list[str]) -> str:
    """Format a list of strings as a TOML array."""
    return "[" + ", ".join(fmt(s) for s in items) + "]"


def parse_ranges(val: str | list[str] | None) -> list[tuple[float, float]] | None:
    """Parse one or more ``lo,hi`` ranges into a list of ``(float, float)``."""
    if val is None:
        return None
    if isinstance(val, list):
        segments = [str(item) for item in val]
    else:
        segments = str(val).split(";")
    result = []
    for seg in segments:
        parts = seg.split(",")
        if len(parts) != 2:
            raise ValueError(f"Expected 'lo,hi' in segment '{seg}'")
        result.append((float(parts[0]), float(parts[1])))
    return result
