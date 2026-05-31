# src/fdtr/fit/freq.py
"""FreqFitter — curve fitting engine for frequency-sweep data.

Supports phase and amplitude signals via :class:`SignalType`, and multi-range
fitting (non-contiguous frequency bands concatenated into a single residual).
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares

from fdtr.model.h2d import h2d
from fdtr.model.layer import MultilayerStack
from fdtr.common_types import FitResult, FitTarget, SignalType
from fdtr.model.param import apply_params, validate_targets


class FreqFitter:
    """Curve fitting engine for freq-sweep data.

    Args:
        stack: Initial MultilayerStack (template).
        signal: Which signal channel to compare (PHASE or AMPLITUDE).
        spot_size_um: Beam 1/e^2 radius in micrometres.
        freq_ranges: List of (f_min, f_max) tuples defining fitting bands.
        n_points: Number of log-spaced points *per range* for interpolation.
    """

    def __init__(
        self,
        stack: MultilayerStack,
        signal: SignalType,
        spot_size_um: float | None,
        freq_ranges: List[tuple[float, float]],
        n_points: int = 80,
    ) -> None:
        self._stack = stack
        self._signal = signal
        if spot_size_um is None:
            raise ValueError(
                "spot_size_um is required for freqfit. Set [fit] spot_size "
                "in the config. Directional spot_x/spot_y are only used by "
                "iterfit pipeline spot_key steps or directional spotfit."
            )
        self._spot_size_um = float(spot_size_um)
        self._freq_ranges = freq_ranges
        self._n_points = n_points

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        freq_data: np.ndarray,
        signal_data: np.ndarray,
        targets: Sequence[FitTarget],
        tol: float = 1e-6,
        max_nfev: int = 200,
    ) -> FitResult:
        """Fit arbitrary parameters against freq-sweep data.

        Args:
            freq_data: Measured frequencies [Hz].
            signal_data: Measured signal (phase [deg] or amplitude).
            targets: Sequence of FitTarget descriptors.
            tol: Tolerance for convergence (ftol, xtol, gtol).
            max_nfev: Maximum number of function evaluations.

        Returns:
            FitResult with fitted physical values and diagnostics.
        """
        resolved = validate_targets(targets, self._stack, allow_spot=True)

        target_map = {t.name: t for t in targets}
        ordered = sorted(target_map.keys())
        x0 = np.array([target_map[n].initial_guess for n in ordered])
        lb = np.array([target_map[n].bounds[0] for n in ordered])
        ub = np.array([target_map[n].bounds[1] for n in ordered])

        # Pre-process data onto concatenated log-spaced grids
        preprocessed = self._preprocess(freq_data, signal_data)

        def residuals(x: np.ndarray) -> np.ndarray:
            params = {
                n: x[i] * target_map[n].scale for i, n in enumerate(ordered)
            }
            new_stack, new_spot = apply_params(
                self._stack, self._spot_size_um, params, resolved,
            )
            w_um = new_spot if new_spot is not None else self._spot_size_um
            return preprocessed["residual_fn"](new_stack, w_um)

        opt = least_squares(
            residuals, x0, bounds=(lb, ub),
            method="trf", ftol=tol, xtol=tol, gtol=tol, max_nfev=max_nfev,
        )

        fitted_values = {
            n: opt.x[i] * target_map[n].scale for i, n in enumerate(ordered)
        }
        fitted_stack, _ = apply_params(
            self._stack, self._spot_size_um, fitted_values, resolved,
        )

        return FitResult(
            fitted_values=fitted_values,
            residual=float(np.sum(opt.fun ** 2)),
            success=opt.success,
            nfev=opt.nfev,
            message=opt.message,
            fitted_stack=fitted_stack,
        )

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------

    def _preprocess(
        self, freq_data: np.ndarray, signal_data: np.ndarray,
    ) -> dict:
        """PCHIP-interpolate data onto log-spaced grids per range, concatenate."""
        freq_data = np.asarray(freq_data, dtype=np.float64).ravel()
        signal_data = np.asarray(signal_data, dtype=np.float64).ravel()

        # Sort by frequency for interpolation
        sort_idx = np.argsort(freq_data)
        freq_sorted = freq_data[sort_idx]
        signal_sorted = signal_data[sort_idx]

        # Build concatenated grid and interpolated values
        omega_parts: list[np.ndarray] = []
        signal_parts: list[np.ndarray] = []

        for f_lo, f_hi in self._freq_ranges:
            grid = np.logspace(np.log10(f_lo), np.log10(f_hi), self._n_points)
            interp = PchipInterpolator(freq_sorted, signal_sorted)
            signal_grid = interp(grid)
            omega_parts.append(2.0 * np.pi * grid)
            signal_parts.append(signal_grid)

        omega_grid = np.concatenate(omega_parts)
        signal_grid = np.concatenate(signal_parts)

        signal = self._signal

        if signal is SignalType.PHASE:
            def residual_fn(stack: MultilayerStack, w_um: float) -> np.ndarray:
                w = w_um * 1e-6
                response = h2d(omega_grid, w0=w, w1=w, sep=0.0, stack=stack)
                model_phase = np.degrees(np.angle(response))
                return signal_grid - model_phase
        else:
            # Amplitude: normalize both data and model by respective max
            data_max = np.max(np.abs(signal_grid))
            if data_max > 0:
                data_norm = signal_grid / data_max
            else:
                data_norm = signal_grid.copy()

            def residual_fn(stack: MultilayerStack, w_um: float) -> np.ndarray:
                w = w_um * 1e-6
                response = h2d(omega_grid, w0=w, w1=w, sep=0.0, stack=stack)
                model_amp = np.abs(response)
                model_max = np.max(np.abs(model_amp))
                if model_max > 0:
                    model_norm = model_amp / model_max
                else:
                    model_norm = model_amp
                return data_norm - model_norm

        return {"residual_fn": residual_fn}
