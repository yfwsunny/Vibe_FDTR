# src/fdtr/fit/offset.py
"""OffsetFitter — curve fitting engine for beam-offset (spatial) data.

Supports phase and amplitude signals via :class:`SignalType`, and multi-range
fitting (non-contiguous offset bands concatenated into a single residual).

Both signals follow the same preprocessing flow:
center peak → PCHIP-interpolate onto dense grid → compare.
"""

from __future__ import annotations

from typing import List, Sequence
import warnings

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares

from fdtr.model.h2d import h2d
from fdtr.model.layer import MultilayerStack
from fdtr.common_types import FitResult, FitTarget, SignalType
from fdtr.model.param import apply_params, validate_targets
from fdtr.fit.offsetcenter_cal import estimate_offset_center, resolve_center_amp


class OffsetFitter:
    """Curve fitting engine for beam-offset data.

    Args:
        stack: Initial MultilayerStack (template).
        signal: Which signal channel to compare (PHASE or AMPLITUDE).
        freq: Modulation frequency in Hz (scalar).
        spot_size_um: Beam 1/e^2 radius in micrometres.
        offset_ranges: List of (offset_min, offset_max) tuples defining fitting
            bands in centred-offset coordinates (micrometres). Points outside
            all ranges are masked out.
        sep_um: Fixed pump-probe separation in micrometres (default 0).
        n_points: Number of linearly-spaced points for the dense interpolation
            grid (total across all ranges).
    """

    def __init__(
        self,
        stack: MultilayerStack,
        signal: SignalType,
        freq: float,
        spot_size_um: float | None,
        offset_ranges: List[tuple[float, float]],
        sep_um: float = 0.0,
        n_points: int = 100,
    ) -> None:
        self._stack = stack
        self._signal = signal
        self._freq = freq
        if spot_size_um is None:
            raise ValueError(
                "spot_size_um is required for offsetfit. Set [fit] spot_size "
                "in the config. Directional spot_x/spot_y are only used by "
                "iterfit pipeline spot_key steps or directional spotfit."
            )
        self._spot_size_um = float(spot_size_um)
        self._offset_ranges = offset_ranges
        self._sep_um = sep_um
        self._n_points = n_points

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        offset_data: np.ndarray,
        signal_data: np.ndarray,
        targets: Sequence[FitTarget],
        center_amp_data: np.ndarray | None = None,
        tol: float = 1e-6,
        max_nfev: int = 200,
    ) -> FitResult:
        """Fit arbitrary parameters against offset-scan data.

        Args:
            offset_data: Measured beam offsets [um].
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

        # Pre-process data onto dense grid
        preprocessed = self._preprocess(
            offset_data, signal_data, center_amp_data=center_amp_data,
        )

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

        for i, n in enumerate(ordered):
            if opt.active_mask[i]:
                print(f"Warning: fitted {n}={opt.x[i]*target_map[n].scale:.4g} hit its "
                      f"{'upper' if opt.active_mask[i] > 0 else 'lower'} bound; widen it and re-run.")

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
        self,
        offset_data: np.ndarray,
        signal_data: np.ndarray,
        center_amp_data: np.ndarray | None = None,
    ) -> dict:
        """Center full-range data first, then sample selected fit windows."""
        offset_data = np.asarray(offset_data, dtype=np.float64).ravel()
        signal_data = np.asarray(signal_data, dtype=np.float64).ravel()
        center_amp = resolve_center_amp(
            offset_data,
            signal_data,
            center_amp_data=center_amp_data,
        )

        center_offset = estimate_offset_center(offset_data, center_amp)
        if abs(center_offset) > 0.1:
            warnings.warn(
                f"Estimated offset center is {center_offset:.4g} um from 0.",
                UserWarning,
                stacklevel=2,
            )
        raw_sort_idx = np.argsort(offset_data)
        signal_interp_full = PchipInterpolator(
            offset_data[raw_sort_idx],
            signal_data[raw_sort_idx],
        )
        signal_peak = float(signal_interp_full(center_offset))
        centered_offset_full = offset_data - center_offset
        centered_signal_full = signal_data - signal_peak

        sort_idx = np.argsort(centered_offset_full)
        centered_offset_full = centered_offset_full[sort_idx]
        centered_signal_full = centered_signal_full[sort_idx]

        ranges_used = [
            (min(float(lo), float(hi)), max(float(lo), float(hi)))
            for lo, hi in self._offset_ranges
        ]
        if not ranges_used:
            ranges_used = [
                (
                    float(centered_offset_full.min()),
                    float(centered_offset_full.max()),
                ),
            ]

        ranges_used.sort(key=lambda r: r[0])

        mask = np.zeros(len(centered_offset_full), dtype=bool)
        for lo, hi in ranges_used:
            mask |= (centered_offset_full >= lo) & (centered_offset_full <= hi)
        if np.count_nonzero(mask) < 2:
            raise ValueError("Not enough data points after offset_ranges filtering.")

        segments: list[tuple[float, float]] = []
        lengths: list[float] = []
        for lo, hi in ranges_used:
            seg_mask = (centered_offset_full >= lo) & (centered_offset_full <= hi)
            if np.count_nonzero(seg_mask) < 2:
                raise ValueError(
                    f"Not enough data points in offset range [{lo:.4g}, {hi:.4g}] after filtering."
                )
            if hi <= lo:
                raise ValueError(
                    f"Invalid offset range after centering: [{lo:.4g}, {hi:.4g}]"
                )
            segments.append((lo, hi))
            lengths.append(hi - lo)

        if self._n_points < len(segments):
            raise ValueError(
                f"n_points={self._n_points} is smaller than number of offset ranges={len(segments)}."
            )

        if len(segments) == 1:
            points_per_segment = [self._n_points]
        else:
            lengths_arr = np.asarray(lengths, dtype=np.float64)
            raw_counts = self._n_points * lengths_arr / np.sum(lengths_arr)
            points_per_segment = np.floor(raw_counts).astype(int)
            points_per_segment = np.maximum(points_per_segment, 1)

            deficit = self._n_points - int(np.sum(points_per_segment))
            if deficit > 0:
                remainders = raw_counts - np.floor(raw_counts)
                order = np.argsort(-remainders)
                for i in order[:deficit]:
                    points_per_segment[i] += 1
            elif deficit < 0:
                remainders = raw_counts - np.floor(raw_counts)
                order = np.argsort(remainders)
                to_remove = -deficit
                for i in order:
                    if to_remove == 0:
                        break
                    if points_per_segment[i] > 1:
                        points_per_segment[i] -= 1
                        to_remove -= 1

            points_per_segment = points_per_segment.tolist()

        data_interp = PchipInterpolator(centered_offset_full, centered_signal_full)
        offset_parts: list[np.ndarray] = []
        signal_parts: list[np.ndarray] = []
        for (seg_lo, seg_hi), n_seg in zip(segments, points_per_segment):
            grid = np.linspace(seg_lo, seg_hi, int(n_seg))
            offset_parts.append(grid)
            signal_parts.append(data_interp(grid))

        dense_offset = np.concatenate(offset_parts)
        signal_dense = np.concatenate(signal_parts)
        omega = np.array([2.0 * np.pi * self._freq])
        sep_dense = dense_offset * 1e-6
        fixed_sep = self._sep_um * 1e-6
        zero_sep = np.array([fixed_sep], dtype=np.float64)

        signal = self._signal

        if signal is SignalType.PHASE:
            def residual_fn(stack: MultilayerStack, w_um: float) -> np.ndarray:
                w = w_um * 1e-6
                response = h2d(
                    omega, w0=w, w1=w, sep=sep_dense + fixed_sep, stack=stack,
                )
                resp = response[0] if response.ndim > 1 else response
                model = np.degrees(np.angle(resp))

                zero_response = h2d(
                    omega, w0=w, w1=w, sep=zero_sep, stack=stack,
                )
                zero_resp = (
                    zero_response[0, 0]
                    if zero_response.ndim > 1
                    else np.ravel(zero_response)[0]
                )
                phase0 = np.degrees(np.angle(zero_resp))
                model_centered = model - phase0
                return signal_dense - model_centered
        else:
            full_data_scale = np.max(np.abs(centered_signal_full))
            if full_data_scale > 0:
                signal_norm = signal_dense / full_data_scale
            else:
                signal_norm = signal_dense.copy()
            sep_full = centered_offset_full * 1e-6 + fixed_sep

            def residual_fn(stack: MultilayerStack, w_um: float) -> np.ndarray:
                w = w_um * 1e-6
                response = h2d(
                    omega, w0=w, w1=w, sep=sep_dense + fixed_sep, stack=stack,
                )
                resp = response[0] if response.ndim > 1 else response
                model_raw = np.abs(resp)

                full_response = h2d(
                    omega, w0=w, w1=w, sep=sep_full, stack=stack,
                )
                full_resp = full_response[0] if full_response.ndim > 1 else full_response
                model_full = np.abs(full_resp)
                model_peak = np.max(model_full)
                model_centered_full = model_full - model_peak
                full_model_scale = np.max(np.abs(model_centered_full))
                if full_model_scale > 0:
                    model_centered = (model_raw - model_peak) / full_model_scale
                else:
                    model_centered = model_raw - model_peak
                return signal_norm - model_centered

        return {
            "residual_fn": residual_fn,
            "peak_offset": center_offset,
            "centered_offset_full": centered_offset_full,
            "centered_signal_full": centered_signal_full,
            "signal_peak": signal_peak,
        }
