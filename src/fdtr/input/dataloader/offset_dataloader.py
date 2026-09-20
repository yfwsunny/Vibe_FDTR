"""Offset scan data loader for FDTR measurements."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
import numpy as np

@dataclass
class OffsetScanData:
    date: str
    offset: np.ndarray
    frequencies: np.ndarray
    r: np.ndarray
    theta: np.ndarray
    probe_rad: float | None = None
    pump_rad: float | None = None

    @property
    def n_harmonics(self) -> int:
        return len(self.frequencies)

_META_PATTERN = re.compile(r"(Probe rad|Pump rad):\s*([\d.]+)\s*um", re.IGNORECASE)
_FREQ_PATTERN = re.compile(r"\((\d+(?:\.\d+)?)\s*Hz\)")

def load_offset_scan(filepath: str | Path) -> OffsetScanData:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Offset scan file not found: {filepath}")
    lines = filepath.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(f"Expected at least 3 lines, got {len(lines)} in {filepath}")

    line1 = lines[0].rstrip("\t")
    line1_stripped = line1.strip()
    probe_rad = pump_rad = None
    for match in _META_PATTERN.finditer(line1_stripped):
        key = match.group(1).strip().lower()
        value = float(match.group(2))
        if "probe" in key:
            probe_rad = value
        elif "pump" in key:
            pump_rad = value
    # Date is everything before the first metadata match
    first_meta = _META_PATTERN.search(line1_stripped)
    if first_meta:
        date_str = line1_stripped[:first_meta.start()].strip()
    else:
        date_str = line1_stripped

    col_headers = lines[1].rstrip("\t").split("\t")
    frequencies = []
    for hdr in col_headers:
        m = _FREQ_PATTERN.search(hdr)
        if m:
            freq = float(m.group(1))
            if freq not in frequencies:
                frequencies.append(freq)
    n_harmonics = len(frequencies)
    if n_harmonics == 0:
        raise ValueError(f"No frequencies found in column headers")

    raw = []
    for line in lines[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        values = stripped.split("\t")
        raw.append([float(v) for v in values])
    data = np.array(raw)
    if data.shape[1] != 1 + 2 * n_harmonics:
        raise ValueError(f"Expected {1 + 2*n_harmonics} columns, got {data.shape[1]}")

    return OffsetScanData(
        date=date_str, offset=data[:, 0], frequencies=np.array(frequencies),
        r=data[:, 1::2], theta=data[:, 2::2],
        probe_rad=probe_rad, pump_rad=pump_rad,
    )
