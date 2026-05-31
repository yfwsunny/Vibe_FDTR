"""Input preparation for uncertainty analysis.

Consolidates parameter resolution, fit-result loading, and x-data generation
from the former ``uncertainty_params`` and ``uncertainty_io`` modules.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from fdtr.input.config import FitConfig, UncertaintySpec, to_fit_targets, to_stack
from fdtr.input.config.prepare_spot import require_scalar_spot_size
from fdtr.model.layer import MultilayerStack
from fdtr.model.param import ResolvedParam, default_parameter_names, get_param_value, resolve

_DEFAULT_RELATIVE_UNCERTAINTY = 0.05
_SPOT_NAMES = frozenset({"spot_size", "spot_x", "spot_y"})
_LAYER_PROPS = frozenset({"Sr", "Sz", "d", "rho_cp"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UncertaintyInputs:
    """Fully resolved inputs ready for the uncertainty engine."""
    target_params: List[ResolvedParam]
    known_params: Dict  # name -> {value, uncertainty, absolute_uncertainty}
    stack: MultilayerStack
    analysis_kind: str
    x_data: np.ndarray
    return_full: bool


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

def _infer_target_param_names_from_config(config: FitConfig) -> list[str]:
    """Infer uncertainty targets from fit targets declared in the base config."""
    return [target.name for target in to_fit_targets(config)]


def _merged_known_param_config(
    config: FitConfig,
    target_param_names: list,
    overrides: dict,
) -> dict:
    """Auto-fill known_params from physical params, apply user overrides."""
    stack = to_stack(config)
    default_names = set(default_parameter_names(stack))
    for name in overrides:
        resolve(name, stack)
    valid_names = default_names
    target_params = [resolve(name, stack) for name in target_param_names]
    target_name_set = set(target_param_names)
    for param in target_params:
        if param.kind == "S":
            target_name_set.add(f"Sr_{param.layer_index}")
            target_name_set.add(f"Sz_{param.layer_index}")

    invalid = sorted(name for name in overrides if name not in valid_names)
    if invalid:
        raise ValueError("Invalid known_params entries: " + ", ".join(invalid))

    merged = {
        name: _DEFAULT_RELATIVE_UNCERTAINTY
        for name in default_names
        if name not in target_name_set
    }
    for name, value in overrides.items():
        if name in valid_names and name not in target_name_set:
            merged[name] = value
    return merged


def resolve_uncertainty_params(
    config: FitConfig,
    uncertainty_config,
) -> Tuple[List[ResolvedParam], Dict]:
    """Resolve target and known parameters for uncertainty calculation.

    Args:
        config: FitConfig object
        uncertainty_config: UncertaintySpec object or raw dict with
            'target_params' and 'known_params'

    Auto-fills known_params from all physical parameters not in target_params.
    User-provided known_params override the default 5% uncertainty.
    """
    if isinstance(uncertainty_config, UncertaintySpec):
        target_param_names = list(uncertainty_config.target_params)
        known_param_overrides = dict(uncertainty_config.known_params)
    else:
        target_param_names = list(uncertainty_config.get("target_params", []))
        known_param_overrides = dict(uncertainty_config.get("known_params", {}))

    if not target_param_names:
        target_param_names = _infer_target_param_names_from_config(config)
    if not target_param_names:
        raise ValueError(
            "uncertainty target_params is empty; provide target_params or set "
            "fit_* targets in the base config."
        )

    spot_size_um = require_scalar_spot_size(config, "uncertainty analysis")
    stack = to_stack(config)
    target_params = [resolve(name, stack) for name in target_param_names]
    merged_known = _merged_known_param_config(
        config,
        [param.raw_name for param in target_params],
        known_param_overrides,
    )

    known_params = {}
    for param_name, rel_uncertainty in merged_known.items():
        value = get_param_value(stack, param_name, spot_size_um=spot_size_um)
        known_params[param_name] = {
            "value": value,
            "uncertainty": rel_uncertainty,
            "absolute_uncertainty": value * rel_uncertainty,
        }

    return target_params, known_params


# ---------------------------------------------------------------------------
# X-data generation
# ---------------------------------------------------------------------------

def _generate_x_data(
    analysis_kind: str,
    fit_config: FitConfig,
    config_dict: dict,
    n_points: int = 80,
    ranges: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """Generate synthetic x_data for the given analysis kind.

    Args:
        ranges: If provided, use these ranges directly instead of
            reading from fit_config / config_dict.
    """
    if analysis_kind == "freq":
        if ranges is not None:
            f_min, f_max = ranges[0]
        elif fit_config.freq_ranges:
            f_min, f_max = fit_config.freq_ranges[0]
        else:
            freq_config = config_dict.get("freq_sweep", {})
            freq_ranges_raw = freq_config.get("freq_ranges", [[5e4, 2e7]])
            f_min, f_max = freq_ranges_raw[0]
        return np.logspace(np.log10(f_min), np.log10(f_max), n_points)
    if analysis_kind in {"offset", "fwhm"}:
        if analysis_kind == "fwhm":
            o_min, o_max = -15.0, 15.0
        elif ranges is not None:
            o_min, o_max = ranges[0]
        elif fit_config.offset_ranges:
            o_min, o_max = fit_config.offset_ranges[0]
        else:
            offset_config = config_dict.get("offset_scan", {})
            o_min, o_max = offset_config.get("offset_ranges", [[-15.0, 15.0]])[0]
        return np.linspace(o_min, o_max, n_points)
    raise ValueError(f"Unknown uncertainty analysis kind: {analysis_kind}")


def _fit_result_strategy(fit_result_config: dict) -> str | None:
    strategy = fit_result_config.get("strategy")
    if strategy:
        return str(strategy)
    fit_strategy = fit_result_config.get("fit", {}).get("strategy")
    if fit_strategy:
        return str(fit_strategy)
    return None


def resolve_uncertainty_analysis_kind(config) -> str:
    """Resolve the internal uncertainty calculation kind from config strategy."""
    if isinstance(config, dict):
        strategy = _fit_result_strategy(config)
    else:
        strategy = getattr(config, "strategy", None)

    if strategy == "freqfit":
        return "freq"
    if strategy == "offsetfit":
        return "offset"
    if strategy == "spotfit":
        return "fwhm"
    if strategy == "iterfit":
        raise ValueError(
            "Iterfit uncertainty must be resolved from pipeline steps, "
            "not through single-run uncertainty preparation."
        )
    raise ValueError(f"Unsupported uncertainty strategy: {strategy!r}")


# ---------------------------------------------------------------------------
# Top-level preparation
# ---------------------------------------------------------------------------

def prepare_uncertainty(
    config,
    x_data: Optional[np.ndarray] = None,
) -> UncertaintyInputs:
    """Build all inputs required by the uncertainty engine.

    Args:
        config: Full config dictionary or FitConfig object.
        x_data: Optional experimental x data. If None, generated from config.

    Returns:
        An :class:`UncertaintyInputs` ready for the engine.
    """
    from fdtr.input.config.config_io import _from_dict

    # Convert dict to FitConfig if needed
    if isinstance(config, dict):
        fit_config = _from_dict(config)
        config_dict = config
    else:
        fit_config = config
        config_dict = {}

    uncertainty_config = fit_config.uncertainty or config_dict.get("uncertainty", {})
    if isinstance(uncertainty_config, dict):
        return_full = uncertainty_config.get("full_output", False)
    else:
        return_full = uncertainty_config.full_output
    analysis_kind = resolve_uncertainty_analysis_kind(config)

    if analysis_kind == "offset":
        offset_config = config_dict.get("offset_scan", {})
        if fit_config.freq_offset is None:
            fit_config.freq_offset = offset_config.get("freq", 1e6)

    # Resolve parameters
    target_params, known_params = resolve_uncertainty_params(fit_config, uncertainty_config)

    stack = to_stack(fit_config)

    # Generate x data if not provided
    if x_data is None:
        import sys as _sys
        if analysis_kind == "freq":
            if fit_config.freq_ranges:
                f_min, f_max = fit_config.freq_ranges[0]
            else:
                print("Warning: freq_ranges not set in config, using default [5e4, 2e7] Hz.", file=_sys.stderr)
                f_min, f_max = 5e4, 2e7
            n_points = fit_config.phase_points or 80
            x_data = np.logspace(np.log10(f_min), np.log10(f_max), n_points)
        elif analysis_kind == "offset":
            if fit_config.offset_ranges:
                o_min, o_max = fit_config.offset_ranges[0]
            else:
                print("Warning: offset_ranges not set in config, using default [-15, 15] um.", file=_sys.stderr)
                o_min, o_max = -15.0, 15.0
            n_points = fit_config.offset_points or 20
            x_data = np.linspace(o_min, o_max, n_points)
        elif analysis_kind == "fwhm":
            n_points = fit_config.offset_points or 100
            x_data = _generate_x_data("fwhm", fit_config, config_dict, n_points)

    return UncertaintyInputs(
        target_params=target_params,
        known_params=known_params,
        stack=stack,
        analysis_kind=analysis_kind,
        x_data=x_data,
        return_full=return_full,
    )


# ---------------------------------------------------------------------------
# Fit-result loading
# ---------------------------------------------------------------------------

def _load_iterfit_result(fit_result: dict) -> Tuple[Dict, None]:
    """Return minimal config for iterfit uncertainty — layers come from --config."""
    config = {
        "strategy": "iterfit",
        "fit": {"strategy": "iterfit"},
        "uncertainty": {"known_params": {}},
    }
    return config, None


def load_fit_result(filepath: str) -> Tuple[Dict, Optional[np.ndarray], Dict]:
    """Load fit result file and extract fitted parameter values.

    Args:
        filepath: Path to fit result JSON file

    Returns:
        (config, x_data, fitted_values) tuple.
        For iterfit: config is minimal (layers come from --config merge).
        For single-fit: config is minimal (layers come from --config merge).
        fitted_values: dict of fitted parameters.
    """
    with open(filepath, "r") as f:
        fit_result = json.load(f)

    # Iterfit: read final_values
    if fit_result.get("strategy") == "iterfit":
        config, _ = _load_iterfit_result(fit_result)
        fitted = fit_result.get("final_values", {})
        return config, None, fitted

    # Single-fit: read fitted_values
    fitted = fit_result.get("fitted_values") or fit_result.get("optimal_params", {})

    config = {
        "uncertainty": {
            "target_params": list(fitted.keys()),
            "known_params": {},
        },
        "layer": [],
        "fit": {},
    }
    return config, None, fitted


def update_layers_from_params(layers: list, params: dict) -> None:
    """Update layer dicts in-place with fitted parameter values.

    Handles parameter names like ``S_2`` -> ``layers[2]["Sr"]`` and
    ``layers[2]["Sz"]``, ``Sr_2`` -> ``layers[2]["Sr"]``,
    ``TBC_1`` -> ``layers[1]["Sr"]`` and ``layers[1]["Sz"]``.
    Spot-related params (spot_x, spot_y, spot_size) are skipped.
    """
    for param_name, value in params.items():
        if param_name in _SPOT_NAMES:
            continue
        if param_name.startswith("TBC_"):
            try:
                idx = int(param_name[4:])
            except ValueError:
                continue
            if 0 <= idx < len(layers):
                if "rho_cp" in layers[idx] and float(layers[idx]["rho_cp"]) != 0.0:
                    raise ValueError(f"{param_name}: layer {idx} is not a TBC layer.")
                layers[idx]["Sr"] = value
                layers[idx]["Sz"] = value
            continue
        if param_name.startswith("S_"):
            try:
                idx = int(param_name[2:])
            except ValueError:
                continue
            if 0 <= idx < len(layers):
                if "S" not in layers[idx]:
                    raise ValueError(
                        f"{param_name}: layer dict uses Sr/Sz; use Sr_{idx} or Sz_{idx} instead."
                    )
                layers[idx]["S"] = value
                layers[idx]["Sr"] = value
                layers[idx]["Sz"] = value
            continue
        parts = param_name.rsplit("_", 1)
        if len(parts) == 2:
            prop, idx_str = parts
            if prop in _LAYER_PROPS:
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                if 0 <= idx < len(layers):
                    if prop in {"Sr", "Sz"} and "S" in layers[idx]:
                        raise ValueError(
                            f"{param_name}: layer dict uses S; use S_{idx} instead."
                        )
                    layers[idx][prop] = value


def validate_fitted_values_against_layer_schema(config_dict: dict, fitted_values: dict) -> None:
    """Validate fitted-value keys against raw layer S/Sr/Sz schema."""
    layers = config_dict.get("layer", [])
    for name in fitted_values:
        if name in {"spot_size", "spot_x", "spot_y"}:
            continue
        if name in {"Sr_substrate", "Sz_substrate", "TBC"}:
            raise ValueError(f"Result key '{name}' is ambiguous; use indexed parameter names.")
        if name.startswith("TBC_") and name[4:].isdigit():
            idx = int(name[4:])
            if idx < len(layers) and float(layers[idx].get("rho_cp", 1.0)) != 0.0:
                raise ValueError(f"Result key '{name}' conflicts with non-TBC layer {idx}.")
            continue
        if name.startswith("S_") and name[2:].isdigit():
            idx = int(name[2:])
            if idx < len(layers) and "S" not in layers[idx]:
                raise ValueError(
                    f"Result key '{name}' conflicts with anisotropic layer that uses Sr/Sz."
                )
            continue
        parts = name.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            prop, idx_text = parts
            idx = int(idx_text)
            if idx < len(layers):
                if prop in {"Sr", "Sz"} and "S" in layers[idx]:
                    raise ValueError(
                        f"Result key '{name}' conflicts with isotropic layer that uses S; "
                        f"use S_{idx} instead."
                    )
                if prop in _LAYER_PROPS and float(layers[idx].get("rho_cp", 1.0)) == 0.0:
                    raise ValueError(f"Result key '{name}' conflicts with TBC layer {idx}.")
