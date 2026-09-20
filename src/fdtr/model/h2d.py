"""H2D thermal response model — ported from MATLAB H2D.m (Aaron Schmidt, 2007).

Supports vectorized ``sep`` for batch computation at multiple pump-probe offsets.
When ``sep`` is a 1-D array, the DC transfer matrix is computed once and the
2-D spatial integration broadcasts over all offset positions, yielding a
significant speed-up over calling in a Python loop.
"""

from __future__ import annotations

import numpy as np
from scipy.special import j0 as besselj0

from fdtr.model.layer import MultilayerStack


def _gauss_legendre(N: int, a: float, b: float):
    """Gauss-Legendre quadrature nodes and weights on [a, b]."""
    nodes, weights = np.polynomial.legendre.leggauss(N)
    half = (b - a) / 2.0
    return half * nodes + (a + b) / 2.0, half * weights


def h2d(
    omega: float | np.ndarray,
    w0: float,
    w1: float,
    sep: float | np.ndarray,
    stack: MultilayerStack,
    num_nodes: int = 30,
) -> np.ndarray:
    """Compute FDTR frequency-domain thermal reflectance response.

    Args:
        omega: Angular frequency [rad/s]. Scalar or 1-D array.
        w0: Pump beam 1/e^2 radius [m].
        w1: Probe beam 1/e^2 radius [m].
        sep: Pump-probe separation [m].
            Scalar for single offset, 1-D array for batch computation.
            ``0`` for coaxial (uses fast 1-D Hankel path).
        stack: MultilayerStack describing the sample.
        num_nodes: Spatial Gauss-Legendre quadrature nodes (default 30).
            K-space nodes are adapted automatically based on the maximum
            pump-probe separation to resolve Bessel oscillations.

    Returns:
        Complex frequency response.
        Shape matches ``omega`` when ``sep`` is scalar.
        Shape ``(N_omega, N_sep)`` when ``sep`` is a 1-D array.
    """
    omega = np.atleast_1d(np.asarray(omega, dtype=np.float64))
    original_shape = omega.shape
    omega = omega.ravel()

    # --- Normalise sep ---
    sep_is_scalar = np.ndim(sep) == 0
    sep_arr = np.atleast_1d(np.asarray(sep, dtype=np.float64)).ravel()
    S = len(sep_arr)

    rho_cp = stack.rho_cp
    Sr = stack.Sr
    Sz = stack.Sz
    d = stack.d
    N_layers = stack.num_layers

    k_upper = 16.0 / np.sqrt(w0**2 + w1**2)

    # J0(k·r_pump) oscillates with period ~2π/r_pump in k-space.
    # At r_pump ≈ max|sep|, the number of oscillation periods in [0, k_upper]
    # is ~k_upper·max|sep|/π.  Gauss-Legendre needs ≥1 node per period for
    # accurate quadrature, so we scale num_k proportionally.  A 1.1× safety
    # margin covers off-center spatial points where r_pump > |sep|.
    max_abs_sep = float(np.max(np.abs(sep_arr)))
    num_k = max(num_nodes, int(np.ceil(1.1 * k_upper * max_abs_sep / np.pi)))
    num_k = min(num_k, 150)

    k, wk = _gauss_legendre(num_k, 0.0, k_upper)
    M = len(k)

    len_omega = len(omega)

    # ------------------------------------------------------------------
    # DC transfer matrix — identical for all sep values
    # ------------------------------------------------------------------
    DC = np.zeros((len_omega, M), dtype=np.complex128)

    for m in range(M):
        temp1 = np.ones(len_omega, dtype=np.complex128)
        temp2 = np.zeros(len_omega, dtype=np.complex128)
        temp3 = np.zeros(len_omega, dtype=np.complex128)
        temp4 = np.ones(len_omega, dtype=np.complex128)

        for n in range(N_layers):
            if rho_cp[n] != 0.0:
                q = np.sqrt(
                    (Sr[n] * k[m]**2 + rho_cp[n] * 1j * omega) / Sz[n]
                )
                qd = q * d[n]
                with np.errstate(over='ignore', invalid='ignore'):
                    x = np.tanh(qd)
                x = np.where(np.isfinite(x), x, 1.0 + 0j)

                A = temp1 - temp3 * x / (Sz[n] * q)
                B = temp2 - temp4 * x / (Sz[n] * q)
                C = -Sz[n] * q * x * temp1 + temp3
                D = -Sz[n] * q * x * temp2 + temp4
            else:
                R = d[n] / Sz[n]
                A = temp1 - R * temp3
                B = temp2 - R * temp4
                C = temp3
                D = temp4

            temp1, temp2, temp3, temp4 = A, B, C, D

        DC[:, m] = -temp4 / temp3

    # ------------------------------------------------------------------
    # Fast path: single sep == 0  (1-D Hankel integral)
    # ------------------------------------------------------------------
    if S == 1 and sep_arr[0] == 0.0:
        gauss_env = np.exp(-k**2 * (w0**2 + w1**2) / 8.0)
        integrand = k * gauss_env * DC
        freq_response = integrand @ wk
        return freq_response.reshape(original_shape)

    # ------------------------------------------------------------------
    # 2-D spatial integration — vectorised over sep
    # ------------------------------------------------------------------
    int_range = 3.0 * w1
    x_nodes, wx = _gauss_legendre(num_nodes, -int_range, int_range)
    y_nodes, wy = _gauss_legendre(num_nodes, 0.0, int_range)

    gauss_env_pump = np.exp(-k**2 * w0**2 / 8.0)          # (M,)
    # Pre-weight DC with k, gaussian envelope and k-weights for matmul
    weighted_DC = DC * (k * gauss_env_pump * wk)[np.newaxis, :]  # (len_omega, M)

    # Output accumulator: (len_omega, num_x, S)
    Tx = np.zeros((len_omega, len(x_nodes), S), dtype=np.complex128)

    for ni, xn in enumerate(x_nodes):
        Ty = np.zeros((len_omega, len(y_nodes), S), dtype=np.complex128)

        for mi, yn in enumerate(y_nodes):
            r_pump = np.sqrt((xn - sep_arr)**2 + yn**2)      # (S,)
            bessel_vals = besselj0(np.outer(r_pump, k))       # (S, M)
            # (len_omega, M) @ (M, S) -> (len_omega, S)
            inner = weighted_DC @ bessel_vals.T

            r_probe = np.sqrt(xn**2 + yn**2)
            Ty[:, mi, :] = np.exp(-2.0 * r_probe**2 / w1**2) * inner

        # Contract over y_nodes: (O, Y, S), (Y,) -> (O, S)
        Tx[:, ni, :] = np.einsum('oys,y->os', Ty, wy)

    # Contract over x_nodes: (O, X, S), (X,) -> (O, S)
    freq_response = np.einsum('oxs,x->os', Tx, wx)

    if sep_is_scalar:
        return freq_response[:, 0].reshape(original_shape)
    return freq_response
