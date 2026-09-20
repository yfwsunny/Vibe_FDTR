"""Loader for flat analysis TOML files (sensitivity / uncertainty).

Flat analysis TOMLs have all keys at the top level.  They reference a
``base_config`` path (resolved relative to the analysis TOML's parent dir)
and contain only the overrides and analysis-specific fields needed for the
analysis run.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from fdtr.input.config.config_dataclass import (
    FitConfig,
    SensitivitySpec,
    UncertaintySpec,
    normalize_strategy,
)
from fdtr.input.config.config_io import from_toml
from fdtr.input.config.unit_check import (
    check_fit_config_units,
    check_uncertainty_known_params,
)


# ---------------------------------------------------------------------------
# Fit-override keys (top-level scalars / tuples)
# ---------------------------------------------------------------------------

_FIT_SCALAR_OVERRIDES: dict[str, type] = {
    "strategy": str,
    "signal": str,
    "iterations": int,
    "pipeline": str,
    "no_plot": bool,
    "report": bool,
    "average": bool,
    "freq_spot": float,
    "freq_offset": float,
    "offset_points": int,
    "phase_points": int,
    "spot_size": float,
    "spot_x": float,
    "spot_y": float,
}

_RANGES_KEYS = {"freq_ranges", "offset_ranges"}
_REMOVED_RANGE_KEYS = {"offset_range": "offset_ranges"}

# ---------------------------------------------------------------------------
# Path-override keys
# ---------------------------------------------------------------------------

_PATH_OVERRIDES = (
    "offset_dir",
    "offset_dir_y",
    "phase_dir",
    "data_file",
    "data_file_y",
    "offset_pattern",
    "offset_pattern_y",
    "phase_pattern",
    "offset_files",
    "offset_files_y",
    "phase_files",
    "output_dir",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_analysis_config(path: str | Path, analysis_type: str) -> FitConfig:
    """Load a flat analysis TOML and return a fully resolved :class:`FitConfig`.

    Parameters
    ----------
    path:
        Path to the flat analysis TOML file.
    analysis_type:
        Either ``"sensitivity"`` or ``"uncertainty"``.

    Returns
    -------
    FitConfig
        Base config with analysis overrides and analysis spec attached.

    Raises
    ------
    ValueError
        If ``base_config`` is missing or ``analysis_type`` is invalid.
    FileNotFoundError
        If the base config file cannot be found.
    """
    if analysis_type not in ("sensitivity", "uncertainty"):
        raise ValueError(
            f"Invalid analysis_type '{analysis_type}'. "
            "Must be 'sensitivity' or 'uncertainty'."
        )

    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)

    # Resolve base_config path relative to the analysis TOML's parent dir
    base_config_str = data.get("base_config", None)
    if base_config_str is None:
        raise ValueError(
            f"Analysis TOML '{path}' is missing required key 'base_config'."
        )
    base_path = (path.parent / base_config_str).resolve()

    # Load base config
    cfg = from_toml(base_path)

    # Apply fit overrides
    for key, expected_type in _FIT_SCALAR_OVERRIDES.items():
        if key in data:
            val = data[key]
            if not isinstance(val, expected_type):
                raise TypeError(
                    f"Key '{key}' must be {expected_type.__name__}, "
                    f"got {type(val).__name__}"
                )
            if key == "strategy":
                cfg.strategy = normalize_strategy(val)
            else:
                setattr(cfg, key, val)

    for removed_key, replacement in _REMOVED_RANGE_KEYS.items():
        if removed_key in data:
            raise ValueError(
                f"'{removed_key}' is no longer supported. "
                f"Use '{replacement} = [[lo, hi], ...]' instead."
            )

    for key in _RANGES_KEYS:
        if key in data:
            val = data[key]
            ranges = []
            for i, r in enumerate(val):
                if len(r) != 2:
                    raise ValueError(f"'{key}[{i}]' must be a 2-element array")
                ranges.append((r[0], r[1]))
            setattr(cfg, key, ranges)

    # Apply path overrides
    for key in _PATH_OVERRIDES:
        if key in data:
            setattr(cfg, key, data[key])

    # Attach analysis spec
    if analysis_type == "sensitivity":
        cfg.sensitivity = SensitivitySpec(
            parameters=list(data.get("parameters", ["all"])),
            delta=float(data.get("delta", 1e-4)),
            output_dir=data.get("sensitivity_output_dir", data.get("output_dir", None)),
        )
    elif analysis_type == "uncertainty":
        cfg.uncertainty = UncertaintySpec(
            known_params=dict(data.get("known_params", {})),
            target_params=list(data.get("target_params", [])),
            fit_result=data.get("fit_result", None),
            full_output=bool(data.get("full_output", False)),
        )

    cfg.analysis_source_path = str(path.resolve())
    check_fit_config_units(cfg, mode="warning")
    if cfg.uncertainty is not None:
        check_uncertainty_known_params(cfg.uncertainty.known_params, mode="warning")
    return cfg
