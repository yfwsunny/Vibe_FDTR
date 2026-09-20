# src/fdtr/output/result_io.py
"""Unified save/load for FitResult and PipelineResult."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def save_result(result, path: Path, *, extra: dict | None = None) -> Path:
    """Save a FitResult or PipelineResult to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = result.to_dict()
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data, indent=2, cls=_NumpyEncoder), encoding="utf-8")
    return path


def load_result(path: Path):
    """Load a FitResult or PipelineResult from JSON."""
    from fdtr.common_types import FitResult
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if "final_values" in data and "history" in data:
        from fdtr.fit.iterfit import PipelineResult
        return PipelineResult.from_dict(data)
    return FitResult.from_dict(data)
