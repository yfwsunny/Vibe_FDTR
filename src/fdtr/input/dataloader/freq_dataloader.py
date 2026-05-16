"""Frequency sweep data loader for FDTR measurements."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np

@dataclass
class FreqSweepData:
    date: str
    frequency: np.ndarray
    amplitude: np.ndarray
    phase: np.ndarray

    @property
    def n_points(self) -> int:
        return len(self.frequency)

def load_freq_sweep(filepath: str | Path) -> FreqSweepData:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Frequency sweep file not found: {filepath}")
    lines = filepath.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(f"Expected at least 3 lines, got {len(lines)}")
    date_str = lines[0].rstrip("\t").strip()
    raw = []
    for line in lines[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        values = stripped.split("\t")
        raw.append([float(v) for v in values])
    data = np.array(raw)
    if data.shape[1] != 3:
        raise ValueError(f"Expected 3 columns, got {data.shape[1]}")
    return FreqSweepData(date=date_str, frequency=data[:, 0], amplitude=data[:, 1], phase=data[:, 2])
