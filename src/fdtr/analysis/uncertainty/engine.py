"""Pure computation engine for uncertainty analysis.

Contains :class:`UncertaintyResult`, Jacobian computation, and the core
uncertainty propagation algorithm.  Depends on :mod:`prepare` for inputs
and :mod:`model.param` for parameter mutation.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from fdtr.analysis.sensitivity.prepare import SweepSpec, compute_signal
from fdtr.analysis.uncertainty.prepare import (
    UncertaintyInputs,
    _generate_x_data,
    prepare_uncertainty,
    resolve_uncertainty_params,
)
from fdtr.input.config import FitConfig, to_stack
from fdtr.model.layer import MultilayerStack
from fdtr.model.param import ResolvedParam, default_parameter_names, get_param_value, resolve


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class UncertaintyResult:
    """Result of uncertainty calculation."""

    target_params: List[str]
    relative_uncertainties: Dict[str, float]
    known_params: Optional[Dict] = None
    covariance_matrix: Optional[np.ndarray] = None
    parameter_contributions: Optional[Dict[str, Dict[str, float]]] = None
    Ju: Optional[np.ndarray] = None
    Jc: Optional[np.ndarray] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_param_perturbation(
    stack: MultilayerStack,
    spot_size_um: float,
    param: ResolvedParam,
    value: float,
) -> tuple[MultilayerStack, float]:
    """Return a new (stack, spot_size_um) with *param* set to *value*."""
    if param.kind == "spot_size":
        return stack, float(value)

    layers = [dataclasses.replace(layer) for layer in stack.layers]

    if param.kind in {"S", "TBC"}:
        layers[param.layer_index] = dataclasses.replace(
            layers[param.layer_index],
            Sr=value,
            Sz=value,
        )
        return MultilayerStack(layers), float(spot_size_um)

    layers[param.layer_index] = dataclasses.replace(
        layers[param.layer_index],
        **{param.property_name: value},
    )
    return MultilayerStack(layers), float(spot_size_um)


# ---------------------------------------------------------------------------
# Jacobian computation
# ---------------------------------------------------------------------------

def compute_jacobian(
    config: FitConfig,
    params: List[ResolvedParam],
    x_data: np.ndarray,
    analysis_kind: str,
    delta: float = 0.01,
) -> np.ndarray:
    """Compute Jacobian matrix for given parameters.

    Uses ``config.signal`` to determine phase vs amplitude, consistent with
    the sensitivity engine.

    Args:
        config: FitConfig object
        params: List of ResolvedParam objects
        x_data: Array of x values
        analysis_kind: "freq" or "offset"
        delta: Perturbation delta for finite difference

    Returns:
        J: Jacobian matrix (N x M) where N is number of data points,
           M is number of parameters
    """
    stack = to_stack(config)
    if analysis_kind == "freq":
        sweep = SweepSpec(mode="freq", axis_name="frequency_Hz", axis_values=x_data)
    elif analysis_kind == "offset":
        sweep = SweepSpec(mode="offset", axis_name="offset_um", axis_values=x_data)
    else:
        raise ValueError(
            f"Unsupported uncertainty analysis kind: '{analysis_kind}'. "
            f"Use 'freq' or 'offset'."
        )

    spot = config.spot_size or 3.0

    # Compute baseline signal
    baseline = np.asarray(compute_signal(config, stack, spot, sweep), dtype=float)

    J = np.zeros((len(x_data), len(params)))

    for i, param in enumerate(params):
        p0 = get_param_value(stack, param.raw_name, spot_size_um=spot)
        if p0 == 0.0:
            raise ValueError(
                f"Parameter '{param.raw_name}' has zero value, "
                f"cannot compute Jacobian."
            )

        plus_stack, plus_spot = _apply_param_perturbation(
            stack, spot, param, p0 * (1.0 + delta),
        )
        plus_signal = np.asarray(
            compute_signal(config, plus_stack, plus_spot, sweep), dtype=float,
        )

        minus_stack, minus_spot = _apply_param_perturbation(
            stack, spot, param, p0 * (1.0 - delta),
        )
        minus_signal = np.asarray(
            compute_signal(config, minus_stack, minus_spot, sweep), dtype=float,
        )

        J[:, i] = (plus_signal - minus_signal) / (2 * delta * p0)

    return J


def compute_fwhm_jacobian(
    config: FitConfig,
    params: List[ResolvedParam],
    x_data: np.ndarray,
    freq_hz,
    delta: float = 0.01,
) -> np.ndarray:
    """Compute Jacobian matrix for FWHM-based fitting.

    Unlike ``compute_jacobian`` which computes d(signal)/d(param) for a curve,
    this computes d(FWHM)/d(param) -- a scalar derivative per parameter.

    Args:
        config: FitConfig object
        params: List of ResolvedParam objects
        x_data: Offset positions [um] for h2d evaluation
        freq_hz: Frequency [Hz] for h2d evaluation
        delta: Perturbation delta for finite difference

    Returns:
        J: Jacobian matrix (1 x M) -- one row (FWHM is scalar), M parameters
    """
    from fdtr.fit.fwhm_fitter import FWHMFitter
    from fdtr.model.h2d import h2d

    stack = to_stack(config)
    spot = config.spot_size or 3.0
    omega = np.atleast_1d(2.0 * np.pi * freq_hz)

    def _compute_fwhm(stack_: MultilayerStack, spot_um: float) -> float:
        w = spot_um * 1e-6
        resp = h2d(omega, w0=w, w1=w, sep=x_data * 1e-6, stack=stack_)
        amp = np.abs(resp[0])
        return FWHMFitter.fwhm_from_curve(x_data, amp)

    baseline_fwhm = _compute_fwhm(stack, spot)

    J = np.zeros((1, len(params)))
    for i, param in enumerate(params):
        p0 = get_param_value(stack, param.raw_name, spot_size_um=spot)
        if p0 == 0.0:
            raise ValueError(
                f"Parameter '{param.raw_name}' has zero value, "
                f"cannot compute FWHM Jacobian."
            )

        plus_stack, plus_spot = _apply_param_perturbation(
            stack, spot, param, p0 * (1.0 + delta),
        )
        fwhm_plus = _compute_fwhm(plus_stack, plus_spot)

        minus_stack, minus_spot = _apply_param_perturbation(
            stack, spot, param, p0 * (1.0 - delta),
        )
        fwhm_minus = _compute_fwhm(minus_stack, minus_spot)

        J[0, i] = (fwhm_plus - fwhm_minus) / (2 * delta * p0)

    return J


# ---------------------------------------------------------------------------
# Uncertainty propagation
# ---------------------------------------------------------------------------

def calculate_uncertainty(
    Ju: np.ndarray,
    Jc: np.ndarray,
    C: np.ndarray,
) -> np.ndarray:
    """Calculate uncertainty matrix using Jacobian propagation.

    Args:
        Ju: Jacobian matrix of target parameters (N x M)
        Jc: Jacobian matrix of known parameters (N x K)
        C: Covariance matrix of known parameters (K x K)

    Returns:
        U: Uncertainty matrix (M x M), diagonal elements are variances
    """
    JtJ = Ju.T @ Ju
    JtJ_inv = np.linalg.inv(JtJ)

    JcC_JcT = Jc @ C @ Jc.T

    U = JtJ_inv @ Ju.T @ JcC_JcT @ Ju @ JtJ_inv

    return U


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------

def run_uncertainty_engine(
    inputs: UncertaintyInputs,
    config: FitConfig,
) -> UncertaintyResult:
    """Run uncertainty calculation from prepared inputs.

    This is a pure-computation function -- no I/O.
    """
    target_params = inputs.target_params
    known_params = inputs.known_params
    analysis_kind = inputs.analysis_kind
    x_data = inputs.x_data

    target_param_names = [p.raw_name for p in target_params]
    known_param_names = list(known_params.keys())

    stack = to_stack(config)

    # Compute Jacobian for target parameters
    if analysis_kind == "fwhm":
        freq_hz = config.freq_spot
        Ju = compute_fwhm_jacobian(config, target_params, x_data, freq_hz)
    else:
        Ju = compute_jacobian(
            config=config,
            params=target_params,
            x_data=x_data,
            analysis_kind=analysis_kind,
        )

    # Compute Jacobian for known parameters
    known_resolved_params = [
        resolve(name, stack) for name in known_params.keys()
    ]
    if analysis_kind == "fwhm":
        freq_hz = config.freq_spot
        Jc = compute_fwhm_jacobian(config, known_resolved_params, x_data, freq_hz)
    else:
        Jc = compute_jacobian(
            config=config,
            params=known_resolved_params,
            x_data=x_data,
            analysis_kind=analysis_kind,
        )

    # Construct covariance matrix
    C = np.diag([kp["absolute_uncertainty"] ** 2 for kp in known_params.values()])

    # Calculate uncertainty matrix
    U = calculate_uncertainty(Ju, Jc, C)

    # Calculate relative uncertainties
    rel_uncertainties = {}
    for i, param in enumerate(target_params):
        p_val = get_param_value(stack, param.raw_name, spot_size_um=config.spot_size or 0.0)
        rel_uncertainties[param.raw_name] = np.sqrt(U[i, i]) / p_val

    result = UncertaintyResult(
        target_params=target_param_names,
        relative_uncertainties=rel_uncertainties,
        known_params=known_params,
    )

    if inputs.return_full:
        JtJ_inv = np.linalg.inv(Ju.T @ Ju)
        result.covariance_matrix = U
        result.Ju = Ju
        result.Jc = Jc

        # Calculate parameter contributions
        contributions = {}
        for i, target_name in enumerate(target_param_names):
            contrib = {}
            total_var = U[i, i]
            for j, known_name in enumerate(known_param_names):
                Jc_j = Jc[:, j : j + 1]
                var_j = C[j, j]
                contrib_j = (
                    JtJ_inv @ Ju.T @ (var_j * Jc_j @ Jc_j.T) @ Ju @ JtJ_inv
                )[i, i]
                contrib[known_name] = contrib_j / total_var * 100
            contributions[target_name] = contrib
        result.parameter_contributions = contributions

    return result


# ---------------------------------------------------------------------------
# Iterfit uncertainty
# ---------------------------------------------------------------------------

_FITTER_TO_ANALYSIS_KIND = {
    "fwhm": "fwhm",
    "offset": "offset",
    "freq": "freq",
}


def _expand_isotropic_underlying(names: set[str]) -> set[str]:
    expanded = set(names)
    for name in names:
        if name.startswith("S_") and name[2:].isdigit():
            idx = name[2:]
            expanded.add(f"Sr_{idx}")
            expanded.add(f"Sz_{idx}")
    return expanded


def run_iterfit_uncertainty(config) -> dict:
    """Run stepwise uncertainty propagation for iterfit pipeline.

    Iterates multiple passes through the pipeline. On the first pass,
    only user-specified known_params and forward-propagated uncertainties
    are used. On subsequent passes, all computed uncertainties (including
    those from later pipeline steps) feed back into earlier steps,
    capturing cross-parameter dependencies.

    Converges when relative uncertainties stop changing between passes.

    Args:
        config: Full config dictionary (must have fit.strategy="iterfit"
                and pipeline definition).

    Returns:
        Tuple of (resolved_sigma dict, history list).
    """
    from fdtr.input.config.config_io import _from_dict
    from fdtr.fit.iterfit import resolve_pipeline_for_config

    if isinstance(config, dict):
        fit_config = _from_dict(config)
        config_dict = config
    else:
        fit_config = config
        config_dict = {}

    uncertainty_config = fit_config.uncertainty or config_dict.get("uncertainty", {})
    if isinstance(uncertainty_config, dict):
        user_known = uncertainty_config.get("known_params", {})
    else:
        user_known = dict(uncertainty_config.known_params)

    stack = to_stack(fit_config)
    for name in user_known:
        resolve(name, stack)
    pipeline = resolve_pipeline_for_config(fit_config)
    resolved_sigma: dict[str, float] = {}
    history: list[dict[str, float]] = []

    _SPOT_NAMES = frozenset({"spot_size", "spot_x", "spot_y"})

    max_iterations = config_dict.get("uncertainty", {}).get("max_iterations", 5)
    tolerance = config_dict.get("uncertainty", {}).get("tolerance", 1e-3)

    for _iteration in range(max_iterations):
        prev_sigma = dict(resolved_sigma)

        for step in pipeline.steps:
            analysis_kind = _FITTER_TO_ANALYSIS_KIND.get(step.fitter)
            if analysis_kind is None:
                continue
            signal = step.signal or ("amplitude" if analysis_kind == "fwhm" else "phase")

            # Resolve per-step ranges: step > config > default
            if analysis_kind == "freq":
                step_ranges = step.freq_ranges or fit_config.freq_ranges
            elif analysis_kind == "offset":
                step_ranges = step.offset_ranges or fit_config.offset_ranges
            else:
                step_ranges = None  # fwhm: no range filtering

            n_points = fit_config.offset_points if analysis_kind in {"offset", "fwhm"} else fit_config.phase_points
            x_data = _generate_x_data(
                analysis_kind, fit_config, config_dict, n_points,
                ranges=step_ranges,
            )

            # Resolve target params for this step
            target_params = [resolve(name, stack) for name in step.target_names]

            # Base exclusion: current step targets
            exclude_names = set(step.target_names)

            # Determine which single spot param (if any) is relevant
            if exclude_names & _SPOT_NAMES:
                spot_allowed = None
                exclude_names |= _SPOT_NAMES
            else:
                spot_allowed = getattr(step, "spot_key", "spot_size")

            spot_exclude = _SPOT_NAMES - {spot_allowed} if spot_allowed else _SPOT_NAMES

            # Build known params with spot-aware exclusion
            full_exclude = _expand_isotropic_underlying(exclude_names | spot_exclude)
            known_names = [n for n in user_known if n not in full_exclude]
            known_rel = {n: user_known[n] for n in known_names}
            known_exclude = _expand_isotropic_underlying(set(known_names))
            full_exclude |= known_exclude
            for prev_param, rel_sigma in resolved_sigma.items():
                if prev_param not in full_exclude and prev_param not in known_names:
                    known_names.append(prev_param)
                    known_rel[prev_param] = rel_sigma
            full_exclude |= _expand_isotropic_underlying(set(known_names))

            # Auto-fill remaining physical params at 5% default
            all_physical = set(default_parameter_names(stack))
            already_covered = set(known_rel.keys())
            for name in all_physical - full_exclude - already_covered:
                known_names.append(name)
                known_rel[name] = 0.05

            if not known_names:
                continue

            # Compute Jacobians
            if analysis_kind == "fwhm":
                freq_hz = fit_config.freq_spot
                Ju = compute_fwhm_jacobian(fit_config, target_params, x_data, freq_hz)
                known_resolved_params = [resolve(n, stack) for n in known_names]
                Jc = compute_fwhm_jacobian(fit_config, known_resolved_params, x_data, freq_hz)
            else:
                fit_config.signal = signal
                saved_freq_offset = fit_config.freq_offset
                try:
                    if analysis_kind == "offset" and step.freq_offset is not None:
                        fit_config.freq_offset = step.freq_offset
                    Ju = compute_jacobian(fit_config, target_params, x_data, analysis_kind)
                    known_resolved_params = [resolve(n, stack) for n in known_names]
                    Jc = compute_jacobian(fit_config, known_resolved_params, x_data, analysis_kind)
                finally:
                    fit_config.freq_offset = saved_freq_offset

            # Build covariance matrix from relative uncertainties
            abs_uncs = []
            for kn in known_names:
                val = get_param_value(stack, kn, spot_size_um=fit_config.spot_size or 0.0)
                rel = known_rel[kn]
                abs_uncs.append(val * rel)
            C = np.diag([u ** 2 for u in abs_uncs])

            # Calculate uncertainty matrix
            U = calculate_uncertainty(Ju, Jc, C)

            # Store relative uncertainties for this step
            for i, param in enumerate(target_params):
                p_val = get_param_value(stack, param.raw_name, spot_size_um=fit_config.spot_size or 0.0)
                resolved_sigma[param.raw_name] = np.sqrt(U[i, i]) / p_val

            # Consolidate spot_x + spot_y -> spot_size
            if "spot_x" in resolved_sigma and "spot_y" in resolved_sigma:
                resolved_sigma["spot_size"] = (
                    resolved_sigma["spot_x"] + resolved_sigma["spot_y"]
                ) / 2.0

        # Snapshot after full pipeline pass
        history.append(dict(resolved_sigma))

        # Check convergence
        if prev_sigma:
            all_keys = set(prev_sigma) | set(resolved_sigma)
            if all(
                abs(resolved_sigma.get(k, 0) - prev_sigma.get(k, 0)) < tolerance
                for k in all_keys
            ):
                break

    return resolved_sigma, history
