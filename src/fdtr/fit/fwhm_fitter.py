"""FWHM-matching fitter for FDTR offset scan amplitude data.

Recovers beam spot size (or other parameters) by matching the full-width at
half-maximum of the simulated amplitude-vs-offset profile to the measured FWHM.

Uses the MATLAB-inspired approach: evaluate h2d at a sparse set of offset
positions, then PCHIP-interpolate onto a dense 100 000-point grid to determine
FWHM accurately.  The amplitude-vs-offset curve is very smooth (nearly
Gaussian), so ~25 well-spaced h2d evaluations suffice.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize_scalar

from fdtr.model.h2d import h2d
from fdtr.model.layer import MultilayerStack
from fdtr.common_types import FitResult, FitTarget
from fdtr.model.param import apply_params, validate_targets

# Dense grid for FWHM determination via PCHIP interpolation.
_DENSE_FWHM_GRID = 100_000


class FWHMFitter:
    """Fit parameters by matching FWHM of amplitude vs offset.

    Args:
        stack: Initial MultilayerStack (template).
        freq: Measurement frequency [Hz].
        sep_um: Offset positions [micrometres], shape (N,).
        spot_size_um: Default beam 1/e^2 radius [um].
        n_h2d: Number of sparse h2d evaluation points for model FWHM.
            The model amplitude profile is computed at *n_h2d* evenly
            spaced offsets, then PCHIP-interpolated onto a dense grid
            to find the FWHM.  Default 25.
    """

    def __init__(
        self,
        stack: MultilayerStack,
        freq: float,
        sep_um: np.ndarray,
        spot_size_um: float | None = None,
        n_h2d: int = 50,
    ) -> None:
        self._stack = stack
        self._sep_um = np.asarray(sep_um, dtype=np.float64)
        self._omega = np.atleast_1d(2.0 * np.pi * freq)
        self._spot_size_um = spot_size_um
        self._n_h2d = n_h2d
        self._resolved = None

        # Pre-compute sparse evaluation positions for model FWHM
        if len(self._sep_um) > n_h2d:
            self._sparse_idx = np.linspace(
                0, len(self._sep_um) - 1, n_h2d, dtype=int,
            )
            self._sparse_sep = self._sep_um[self._sparse_idx]
        else:
            self._sparse_sep = self._sep_um

        # Pre-compute dense grid within data range
        self._dense_sep = np.linspace(
            self._sep_um.min(), self._sep_um.max(), _DENSE_FWHM_GRID,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        amp_data: np.ndarray,
        targets: FitTarget | list[FitTarget],
        tol: float = 1e-6,
        max_nfev: int = 200,
    ) -> FitResult:
        """Run the FWHM-matching fit."""
        if isinstance(targets, FitTarget):
            targets = [targets]

        resolved = validate_targets(targets, self._stack, allow_spot=True)
        self._resolved = resolved

        target_map = {t.name: t for t in targets}
        ordered = sorted(target_map.keys())

        # Extract data FWHM (computed once from full data)
        fwhm_data = self._compute_fwhm(self._sep_um, amp_data)

        if len(ordered) == 1:
            return self._fit_single(ordered[0], target_map, fwhm_data, tol, max_nfev, resolved)

        return self._fit_multi(ordered, target_map, fwhm_data, tol, max_nfev, resolved)

    # ------------------------------------------------------------------
    # Internal: optimisation
    # ------------------------------------------------------------------

    def _fit_single(
        self, name: str, target_map: dict, fwhm_data: float,
        tol: float, max_nfev: int, resolved: dict,
    ) -> FitResult:
        t = target_map[name]

        def objective(x: float) -> float:
            params = {name: x * t.scale}
            new_stack, new_spot = apply_params(
                self._stack, self._spot_size_um, params, resolved,
            )
            w_um = new_spot if new_spot is not None else self._spot_size_um
            fwhm_model = self._compute_model_fwhm(new_stack, w_um)
            return (fwhm_model - fwhm_data) ** 2

        opt = minimize_scalar(
            objective,
            bounds=(t.bounds[0], t.bounds[1]),
            method="bounded",
            options={"xatol": tol, "maxiter": max_nfev},
        )

        fitted_values = {name: opt.x * t.scale}
        fitted_stack, _ = apply_params(
            self._stack, self._spot_size_um, fitted_values, resolved,
        )
        return FitResult(
            fitted_values=fitted_values,
            residual=float(opt.fun),
            success=bool(opt.success),
            nfev=int(opt.nfev),
            message=str(opt.message) if opt.message else "",
            fitted_stack=fitted_stack,
        )

    def _fit_multi(
        self, ordered: list[str], target_map: dict, fwhm_data: float,
        tol: float, max_nfev: int, resolved: dict,
    ) -> FitResult:
        from scipy.optimize import least_squares

        x0 = np.array([target_map[n].initial_guess for n in ordered])
        lb = np.array([target_map[n].bounds[0] for n in ordered])
        ub = np.array([target_map[n].bounds[1] for n in ordered])

        def residuals(x: np.ndarray) -> np.ndarray:
            params = {n: x[i] * target_map[n].scale for i, n in enumerate(ordered)}
            new_stack, new_spot = apply_params(
                self._stack, self._spot_size_um, params, resolved,
            )
            w_um = new_spot if new_spot is not None else self._spot_size_um
            fwhm_model = self._compute_model_fwhm(new_stack, w_um)
            return np.array([fwhm_model - fwhm_data])

        opt = least_squares(
            residuals, x0, bounds=(lb, ub),
            method="trf", ftol=tol, xtol=tol, gtol=tol, max_nfev=max_nfev,
        )

        fitted_values = {n: opt.x[i] * target_map[n].scale for i, n in enumerate(ordered)}
        fitted_stack, _ = apply_params(
            self._stack, self._spot_size_um, fitted_values, resolved,
        )
        return FitResult(
            fitted_values=fitted_values,
            residual=float(np.sum(opt.fun ** 2)),
            success=bool(opt.success),
            nfev=int(opt.nfev),
            message=str(opt.message) if opt.message else "",
            fitted_stack=fitted_stack,
        )

    # ------------------------------------------------------------------
    # Internal: FWHM computation
    # ------------------------------------------------------------------

    @staticmethod
    def fwhm_from_curve(sep: np.ndarray, amp: np.ndarray) -> float:
        """FWHM from (sep, amp) arrays via PCHIP + dense grid."""
        amp_norm = amp / np.max(np.abs(amp))
        sep_dense = np.linspace(sep.min(), sep.max(), _DENSE_FWHM_GRID)
        interp = PchipInterpolator(sep, amp_norm)
        amp_dense = np.real(interp(sep_dense))
        half_max = np.abs(amp_dense) >= 0.5
        if not np.any(half_max):
            return 0.0
        indices = np.where(half_max)[0]
        return float(abs(sep_dense[indices[-1]]) + abs(sep_dense[indices[0]]))

    def _compute_fwhm(self, sep: np.ndarray, amp: np.ndarray) -> float:
        """Compute FWHM — delegates to static helper."""
        return self.fwhm_from_curve(sep, amp)

    def _compute_model_fwhm(
        self, stack: MultilayerStack, spot_size_um: float | None = None,
    ) -> float:
        """Compute model FWHM: sparse h2d → PCHIP → dense grid → FWHM."""
        w_um = spot_size_um if spot_size_um is not None else self._spot_size_um
        if w_um is None:
            raise ValueError(
                "spot_size_um must be provided (via constructor or as a fit target)"
            )
        w = w_um * 1e-6
        # Evaluate h2d at sparse positions
        resp = h2d(self._omega, w0=w, w1=w, sep=self._sparse_sep * 1e-6, stack=stack)
        sparse_amp = np.abs(resp[0])
        # PCHIP interpolate onto dense grid and compute FWHM
        interp = PchipInterpolator(self._sparse_sep, sparse_amp)
        dense_amp = np.real(interp(self._dense_sep))
        dense_amp_norm = dense_amp / np.max(np.abs(dense_amp))
        half_max = np.abs(dense_amp_norm) >= 0.5
        if not np.any(half_max):
            return 0.0
        indices = np.where(half_max)[0]
        return float(abs(self._dense_sep[indices[-1]]) + abs(self._dense_sep[indices[0]]))
