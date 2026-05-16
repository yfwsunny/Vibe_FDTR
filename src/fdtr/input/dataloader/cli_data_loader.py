"""High-level data loading orchestration for the FDTR CLI.

Provides directory-level scanning, multi-file averaging, and resampling
for both frequency-sweep and offset-scan data.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List

import numpy as np
from scipy.interpolate import PchipInterpolator

from fdtr.input.dataloader.data_averaging import average_freq_sweeps, average_offset_scans
from fdtr.input.dataloader.freq_dataloader import load_freq_sweep
from fdtr.input.dataloader.offset_dataloader import load_offset_scan

from fdtr.input.dataloader.validation import (
    _is_valid_offset_file,
    _is_valid_phase_file,
    _glob_case_insensitive,
)


def _filter_files(
    all_files: list[Path],
    pattern: str | None = None,
    explicit_files: list[str] | None = None,
) -> list[Path]:
    """Filter file list by explicit names or glob pattern."""
    if explicit_files:
        explicit_set = set(explicit_files)
        filtered = [f for f in all_files if f.name in explicit_set]
        if len(filtered) != len(explicit_files):
            missing = explicit_set - {f.name for f in filtered}
            print(f"  Warning: Missing explicit files: {sorted(missing)}")
        return filtered
    if pattern:
        return [f for f in all_files if _match_filename(f.name, pattern)]
    return all_files


def _match_filename(name: str, pattern: str) -> bool:
    """Case-insensitive filename glob match."""
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())


def _derive_secondary_offset_pattern(pattern: str | None) -> str | None:
    """Infer the companion logical-Y selector from a logical-X selector."""
    if pattern is None:
        return None
    pairs = (
        ("xscan", "yscan"),
        ("XScan", "YScan"),
        ("XSCAN", "YSCAN"),
        ("yscan", "xscan"),
        ("YScan", "XScan"),
        ("YSCAN", "XSCAN"),
    )
    for old, new in pairs:
        if old in pattern:
            return pattern.replace(old, new)
    return None


def _has_scan_axis_marker(pattern: str | None) -> bool:
    if pattern is None:
        return False
    lower = pattern.lower()
    return "xscan" in lower or "yscan" in lower


def _select_logical_offset_files(
    all_scan_files: list[Path],
    *,
    selector: str | None,
    explicit_files: list[str] | None,
    default_axis_pattern: str,
) -> list[Path]:
    """Select files for one logical axis.

    Axis-specific selectors such as ``*YScan*`` fully define the logical axis.
    Broad selectors such as ``*14mW*`` are combined with the default filename
    axis so existing configs continue to select only XScan for logical X and
    only YScan for logical Y.
    """
    if explicit_files:
        return _filter_files(all_scan_files, explicit_files=explicit_files)
    if selector is None:
        return _filter_files(all_scan_files, pattern=default_axis_pattern)
    files = _filter_files(all_scan_files, pattern=selector)
    if _has_scan_axis_marker(selector):
        return files
    return _filter_files(files, pattern=default_axis_pattern)


def _resample_offset(scan, n_points: int):
    """PCHIP-resample an offset scan onto a uniform grid of *n_points*."""
    if n_points <= 0 or len(scan.offset) <= n_points:
        return scan
    new_offset = np.linspace(scan.offset.min(), scan.offset.max(), n_points)
    n_harm = scan.r.shape[1]
    r_new = np.zeros((n_points, n_harm))
    theta_new = np.zeros((n_points, n_harm))
    r_std_new = np.zeros((n_points, n_harm))
    theta_std_new = np.zeros((n_points, n_harm))
    for h in range(n_harm):
        r_new[:, h] = PchipInterpolator(scan.offset, scan.r[:, h])(new_offset)
        theta_new[:, h] = PchipInterpolator(scan.offset, scan.theta[:, h])(new_offset)
        if hasattr(scan, 'r_std') and scan.r_std is not None and len(scan.r_std) > 0:
            r_std_new[:, h] = PchipInterpolator(scan.offset, scan.r_std[:, h])(new_offset)
            theta_std_new[:, h] = PchipInterpolator(scan.offset, scan.theta_std[:, h])(new_offset)
    # Reconstruct same type as input (OffsetScanData or AveragedOffsetScan)
    from fdtr.input.dataloader.data_averaging import AveragedOffsetScan
    if isinstance(scan, AveragedOffsetScan):
        return AveragedOffsetScan(
            offset=new_offset, frequencies=scan.frequencies,
            r=r_new, r_std=r_std_new, theta=theta_new, theta_std=theta_std_new,
            probe_rad=scan.probe_rad, pump_rad=scan.pump_rad,
        )
    # Plain OffsetScanData — just return with resampled arrays
    scan.offset = new_offset
    scan.r = r_new
    scan.theta = theta_new
    return scan


def _resample_freq(freq: np.ndarray, phase: np.ndarray,
                   amplitude: np.ndarray | None = None,
                   n_points: int = 80):
    """Resample (freq, phase[, amplitude]) onto log-spaced grid."""
    if n_points <= 0 or len(freq) <= n_points:
        if amplitude is not None:
            return freq, phase, amplitude
        return freq, phase
    new_freq = np.logspace(np.log10(freq.min()), np.log10(freq.max()), n_points)
    new_phase = PchipInterpolator(freq, phase)(new_freq)
    if amplitude is not None:
        new_amp = PchipInterpolator(freq, amplitude)(new_freq)
        return new_freq, new_phase, new_amp
    return new_freq, new_phase


def _load_offset_scan_data(
    data_dir: Path,
    average: bool = True,
    n_points: int = 100,
    pattern: str | None = None,
    explicit_files: list[str] | None = None,
    pattern_y: str | None = None,
    explicit_files_y: list[str] | None = None,
) -> dict:
    """Load offset scan files from *data_dir* into logical X/Y fit axes.

    Args:
        data_dir: Directory to search for offset scan files.
        average: Whether to average multiple files.
        n_points: Target number of offset points after resampling.
        pattern: Glob pattern for logical-X file selection.
        explicit_files: Explicit logical-X filenames (overrides pattern).
        pattern_y: Glob pattern for logical-Y file selection.
        explicit_files_y: Explicit logical-Y filenames.

    After averaging, resamples onto a uniform grid of *n_points* offset
    positions (default 100).
    """
    result: dict = {}

    # The returned X/Y buckets are logical fitting axes. Filename XScan/YScan
    # labels are only defaults and can be swapped by config patterns/files.
    all_scan_files = [
        f for f in _glob_case_insensitive(data_dir, "*scan*", ".txt")
        if _is_valid_offset_file(str(f))
    ]

    effective_pattern_x = pattern or "*xscan*"
    effective_pattern_y = pattern_y
    if effective_pattern_y is None:
        effective_pattern_y = _derive_secondary_offset_pattern(pattern)
        if effective_pattern_y is None:
            effective_pattern_y = pattern

    for direction, selector, explicit in [
        ("X", effective_pattern_x, explicit_files),
        ("Y", effective_pattern_y, explicit_files_y),
    ]:
        default_axis_pattern = "*xscan*" if direction == "X" else "*yscan*"
        files = _select_logical_offset_files(
            all_scan_files,
            selector=selector,
            explicit_files=explicit,
            default_axis_pattern=default_axis_pattern,
        )
        if not files:
            continue

        if average and len(files) > 1:
            scans = [load_offset_scan(str(f)) for f in files]
            all_offsets = np.concatenate([s.offset for s in scans])
            common_sep = np.unique(all_offsets)
            common_sep = common_sep[np.isfinite(common_sep)]
            avg = average_offset_scans([str(f) for f in files], common_sep)
            result[direction] = avg
            print(f"  Averaged {len(files)} logical {direction} offset files -> {len(avg.offset)} offset points")
        else:
            scan = load_offset_scan(str(files[0]))
            result[direction] = scan
            print(f"  Loaded logical {direction} offset: {files[0].name} ({len(scan.offset)} offsets, "
                  f"{len(scan.frequencies)} harmonics)")

    # Fallback: generic *Scan*.txt if neither X nor Y found
    if not result:
        files = _filter_files(all_scan_files, pattern=pattern, explicit_files=explicit_files)
        if files:
            if average and len(files) > 1:
                scans = [load_offset_scan(str(f)) for f in files]
                all_offsets = np.concatenate([s.offset for s in scans])
                common_sep = np.unique(all_offsets)
                common_sep = common_sep[np.isfinite(common_sep)]
                avg = average_offset_scans([str(f) for f in files], common_sep)
                result["generic"] = avg
                print(f"  Averaged {len(files)} generic Scan files -> {len(avg.offset)} offset points")
            else:
                scan = load_offset_scan(str(files[0]))
                result["generic"] = scan
                print(f"  Loaded generic scan: {files[0].name} ({len(scan.offset)} offsets)")

    if not result:
        raise FileNotFoundError(f"No valid offset scan files found in {data_dir}")

    # Resample to target n_points
    if n_points > 0:
        for d in result:
            old_len = len(result[d].offset)
            result[d] = _resample_offset(result[d], n_points)
            new_len = len(result[d].offset)
            if new_len != old_len:
                print(f"  Resampled {d} direction: {old_len} -> {new_len} points")

    return result


def _load_freq_sweep_data(
    data_dir: Path,
    average: bool = True,
    n_points: int = 80,
    pattern: str | None = None,
    explicit_files: list[str] | None = None,
) -> tuple:
    """Load frequency-sweep .txt files from *data_dir*.

    Args:
        data_dir: Directory to search for freq-sweep files.
        average: Whether to average multiple files.
        n_points: Target number of frequency points after resampling.
        pattern: Glob pattern for file selection (e.g., "sample_A_*.txt").
        explicit_files: Explicit list of filenames to load (overrides pattern).

    After averaging, resamples onto a log-spaced grid of *n_points*
    frequency points (default 80).

    Returns:
        (freq, phase, amplitude) — amplitude may be None if unavailable.
    """
    # Tier 1: Fast path — image_point files
    base_files = sorted(data_dir.glob("*_image_*_point*.txt"))
    if base_files and pattern:
        base_files = [f for f in base_files if Path(f.name).match(pattern)]
    if base_files:
        print(f"  Found {len(base_files)} image_point files (fast path)")

    if not base_files:
        # Tier 2+3: Scan all .txt, exclude Pump_Phase, apply heuristic
        candidates = sorted(data_dir.glob("*.txt"))
        for f in candidates:
            fname = f.name.lower()
            if "pump_phase" in fname:
                print(f"  Skipping (Pump_Phase): {f.name}")
                continue
            if _is_valid_phase_file(str(f)):
                base_files.append(f)
                print(f"  Accepted (heuristic): {f.name}")
            else:
                print(f"  Skipped (phase out of range): {f.name}")

    files = _filter_files(base_files, pattern=pattern, explicit_files=explicit_files)
    if not files:
        raise FileNotFoundError(f"No frequency-sweep .txt files found in {data_dir}")

    if average and len(files) > 1:
        sweeps = [load_freq_sweep(str(fp)) for fp in files]
        all_freq = np.concatenate([s.frequency for s in sweeps])
        common_freq = np.unique(all_freq)
        common_freq = common_freq[np.isfinite(common_freq)]

        averaged = average_freq_sweeps([str(fp) for fp in files], common_freq)
        print(f"  Averaged {len(files)} files -> {len(averaged.frequency)} freq points")

        # Resample
        freq, phase, amp = _resample_freq(
            averaged.frequency, averaged.phase,
            amplitude=averaged.amplitude, n_points=n_points,
        )
        if len(freq) != len(averaged.frequency):
            print(f"  Resampled phase: {len(averaged.frequency)} -> {len(freq)} points")
        return freq, phase, amp

    # Single file or no averaging
    all_freq: List[np.ndarray] = []
    all_phase: List[np.ndarray] = []
    all_amp: List[np.ndarray] = []
    for fp in files:
        sweep = load_freq_sweep(str(fp))
        all_freq.append(sweep.frequency)
        all_phase.append(sweep.phase)
        all_amp.append(sweep.amplitude)

    freq = np.concatenate(all_freq)
    phase = np.concatenate(all_phase)
    amp = np.concatenate(all_amp)

    freq, unique_idx = np.unique(freq, return_index=True)
    phase = phase[unique_idx]
    amp = amp[unique_idx]

    # Resample
    freq, phase, amp = _resample_freq(freq, phase, amplitude=amp, n_points=n_points)
    return freq, phase, amp
