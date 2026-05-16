"""Data directory scanner for grouped FDTR scan-data summaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fdtr.input.dataloader.freq_dataloader import load_freq_sweep
from fdtr.input.dataloader.offset_dataloader import load_offset_scan


_DEFAULT_PATTERNS = {
    "offset_x_glob": "*xscan*",
    "offset_y_glob": "*yscan*",
    "freq_image_glob": "*_image_*_point*.txt",
}

_POWER_AND_SCAN_SUFFIX_RE = re.compile(
    r"(?i)_(?:\d+(?:\.\d+)?(?:uW|mW|W))_(?:\d+(?:\.\d+)?(?:uW|mW|W))(?:_\d+)?_(?:xscan|yscan)$"
)
_POWER_ONLY_SUFFIX_RE = re.compile(
    r"(?i)_(?:\d+(?:\.\d+)?(?:uW|mW|W))_(?:\d+(?:\.\d+)?(?:uW|mW|W))(?:_\d+)?$"
)
_IMAGE_POINT_SUFFIX_RE = re.compile(r"(?i)_image_\d+_point\d+$")
_IMAGE_SUFFIX_RE = re.compile(r"(?i)_image_\d+$")
_SCAN_SUFFIX_RE = re.compile(r"(?i)_(xscan|yscan)$")
_AVERAGE_SUFFIX_RE = re.compile(r"(?i)_average$")


def scan_data_directory(
    data_dir: str | Path,
    *,
    offset_x_glob: str | None = None,
    offset_y_glob: str | None = None,
    freq_image_glob: str | None = None,
    temp_regex: str | None = None,
    group: str | None = None,
    detail_threshold: int | None = 4,
    force_full_detail: bool = False,
) -> dict[str, Any]:
    """Scan a directory for FDTR data files and return grouped metadata."""
    del temp_regex

    data_dir = Path(data_dir).resolve()
    if not data_dir.is_dir():
        return {"error": f"Not a directory: {data_dir}", "directory": str(data_dir)}

    offset_x_files = _ci_glob(data_dir, offset_x_glob or _DEFAULT_PATTERNS["offset_x_glob"])
    offset_y_files = _ci_glob(data_dir, offset_y_glob or _DEFAULT_PATTERNS["offset_y_glob"])
    freq_image_files = sorted(data_dir.glob(freq_image_glob or _DEFAULT_PATTERNS["freq_image_glob"]))

    all_txt = sorted(data_dir.glob("*.txt"))
    excluded = set(offset_x_files + offset_y_files + freq_image_files)
    freq_generic_files = [
        path
        for path in all_txt
        if path not in excluded and "pump_phase" not in path.name.lower()
    ]

    grouped: dict[str, dict[str, Any]] = {}
    for path in offset_x_files:
        _merge_offset_detail(grouped, data_dir, path, "offset_x")
    for path in offset_y_files:
        _merge_offset_detail(grouped, data_dir, path, "offset_y")
    for path in freq_image_files:
        _merge_freq_detail(grouped, data_dir, path, "image_point")
    for path in freq_generic_files:
        _merge_freq_detail(grouped, data_dir, path, "generic_freq")

    group_details = [grouped[key] for key in sorted(grouped)]

    if group is not None:
        detail = grouped.get(_normalize_group_key(group))
        if detail is None:
            return {
                "directory": str(data_dir),
                "error": f"Group not found: {group}",
                "available_groups": [item["group_key"] for item in group_details],
            }
        return detail

    if force_full_detail:
        groups = group_details
    else:
        groups = [{"group_key": item["group_key"]} for item in group_details]

    return {
        "directory": str(data_dir),
        "group_count": len(group_details),
        "groups": groups,
    }


def _ci_glob(directory: Path, pattern: str) -> list[Path]:
    """Case-insensitive glob match for text files."""
    name_re = re.compile(pattern.replace("*", ".*"), re.IGNORECASE)
    return sorted(path for path in directory.glob("*.txt") if name_re.search(path.name))


def _normalize_group_key(name: str) -> str:
    """Collapse file naming noise into a stable group key."""
    key = Path(name).stem
    key = _IMAGE_POINT_SUFFIX_RE.sub("", key)
    key = _IMAGE_SUFFIX_RE.sub("", key)
    key = _POWER_AND_SCAN_SUFFIX_RE.sub("", key)
    key = _POWER_ONLY_SUFFIX_RE.sub("", key)
    key = _SCAN_SUFFIX_RE.sub("", key)
    key = _AVERAGE_SUFFIX_RE.sub("", key)
    key = re.sub(r"__+", "_", key)
    return key.strip("_") or "unknown"


def _group_detail(grouped: dict[str, dict[str, Any]], data_dir: Path, group_key: str) -> dict[str, Any]:
    if group_key not in grouped:
        grouped[group_key] = {
            "directory": str(data_dir),
            "group_key": group_key,
        }
    return grouped[group_key]


def _merge_offset_detail(
    grouped: dict[str, dict[str, Any]],
    data_dir: Path,
    path: Path,
    axis_key: str,
) -> None:
    group_key = _normalize_group_key(path.stem)
    detail = _group_detail(grouped, data_dir, group_key)
    axis_detail = detail.setdefault(
        axis_key,
        {
            "count": 0,
            "pattern": _make_offset_pattern(group_key, axis_key),
            "offset_freqs_hz": [],
            "offset_min_um": None,
            "offset_max_um": None,
        },
    )
    axis_detail["count"] += 1

    try:
        scan = load_offset_scan(path)
    except Exception:
        return

    freq_values = {float(value) for value in axis_detail["offset_freqs_hz"]}
    freq_values.update(float(value) for value in scan.frequencies.tolist())
    axis_detail["offset_freqs_hz"] = sorted(freq_values)

    offset_min = float(scan.offset.min())
    offset_max = float(scan.offset.max())
    axis_detail["offset_min_um"] = (
        offset_min
        if axis_detail["offset_min_um"] is None
        else min(axis_detail["offset_min_um"], offset_min)
    )
    axis_detail["offset_max_um"] = (
        offset_max
        if axis_detail["offset_max_um"] is None
        else max(axis_detail["offset_max_um"], offset_max)
    )


def _merge_freq_detail(
    grouped: dict[str, dict[str, Any]],
    data_dir: Path,
    path: Path,
    name_mode: str,
) -> None:
    group_key = _normalize_group_key(path.stem)
    detail = _group_detail(grouped, data_dir, group_key)
    freq_detail = detail.setdefault(
        "freq_sweep",
        {
            "count": 0,
            "pattern": _make_freq_pattern(group_key, name_mode),
            "freq_min_hz": None,
            "freq_max_hz": None,
            "name_mode": name_mode,
        },
    )
    freq_detail["count"] += 1
    if freq_detail["name_mode"] != name_mode and freq_detail["name_mode"] != "image_point":
        freq_detail["name_mode"] = name_mode
        freq_detail["pattern"] = _make_freq_pattern(group_key, name_mode)

    try:
        sweep = load_freq_sweep(path)
    except Exception:
        return

    freq_min = float(sweep.frequency.min())
    freq_max = float(sweep.frequency.max())
    freq_detail["freq_min_hz"] = (
        freq_min if freq_detail["freq_min_hz"] is None else min(freq_detail["freq_min_hz"], freq_min)
    )
    freq_detail["freq_max_hz"] = (
        freq_max if freq_detail["freq_max_hz"] is None else max(freq_detail["freq_max_hz"], freq_max)
    )


def _make_offset_pattern(group_key: str, axis_key: str) -> str:
    axis = "xscan" if axis_key == "offset_x" else "yscan"
    return f"*{group_key}*{axis}*"


def _make_freq_pattern(group_key: str, name_mode: str) -> str:
    if name_mode == "image_point":
        return f"*{group_key}*image*"
    return f"*{group_key}*"
