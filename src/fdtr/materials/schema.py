"""Material data model with temperature-dependent property interpolation."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union
import warnings
import numpy as np
from scipy.interpolate import PchipInterpolator

from fdtr.model.layer import (
    SYMMETRY_ISOTROPIC,
    SYMMETRY_TRANSVERSE,
    VALID_SYMMETRIES,
)


@dataclass(frozen=True)
class MaterialMetadata:
    """Optional metadata for a material data file."""
    source: str = ""
    author: str = ""
    date: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Material:
    """Temperature-dependent thermal properties for a single material.

    Attributes:
        name: Material name (from filename stem).
        T: Temperature array (K).
        rho_cp: Volumetric heat capacity array (J/m³K).
        Sz: Cross-plane thermal conductivity array (W/mK).
        Sr: In-plane thermal conductivity array (W/mK).
        metadata: Optional source/author metadata.
    """

    name: str
    T: np.ndarray
    rho_cp: np.ndarray
    Sz: np.ndarray
    Sr: np.ndarray
    symmetry: str = SYMMETRY_TRANSVERSE
    metadata: MaterialMetadata | None = None

    def __post_init__(self) -> None:
        if self.symmetry not in VALID_SYMMETRIES:
            raise ValueError(
                f"Material '{self.name}' has invalid symmetry '{self.symmetry}'. "
                f"Expected one of {sorted(VALID_SYMMETRIES)}."
            )
        n = len(self.T)
        if n < 1:
            raise ValueError(f"Material '{self.name}' must have at least 1 data point, got {n}.")
        if not (len(self.rho_cp) == len(self.Sz) == len(self.Sr) == n):
            raise ValueError(f"Material '{self.name}': all property arrays must have same length (T has {n}).")
        object.__setattr__(self, "T", np.asarray(self.T, dtype=np.float64))
        object.__setattr__(self, "rho_cp", np.asarray(self.rho_cp, dtype=np.float64))
        object.__setattr__(self, "Sz", np.asarray(self.Sz, dtype=np.float64))
        object.__setattr__(self, "Sr", np.asarray(self.Sr, dtype=np.float64))
        if self.symmetry == SYMMETRY_ISOTROPIC and not np.allclose(self.Sr, self.Sz):
            raise ValueError(
                f"Material '{self.name}': isotropic symmetry requires Sr and Sz arrays to match."
            )

    @property
    def T_min(self) -> float:
        return float(self.T[0])

    @property
    def T_max(self) -> float:
        return float(self.T[-1])

    @property
    def n_points(self) -> int:
        return len(self.T)

    def get_property_at_T(self, T: Union[float, np.ndarray], property_name: str) -> Union[float, np.ndarray]:
        """Interpolate a property at the given temperature.

        Args:
            T: Temperature or array of temperatures (K).
            property_name: One of 'rho_cp', 'Sz', 'Sr', or isotropic 'S'.

        Returns:
            Interpolated property value(s).
        """
        prop_map = {"rho_cp": self.rho_cp, "Sz": self.Sz, "Sr": self.Sr}
        if property_name == "S":
            if self.symmetry != SYMMETRY_ISOTROPIC:
                raise ValueError(
                    f"Material '{self.name}' is anisotropic; use 'Sr' or 'Sz', not 'S'."
                )
            property_name = "Sr"
        if property_name not in prop_map:
            valid = list(prop_map.keys()) + ["S"]
            raise ValueError(f"Unknown property '{property_name}'. Valid: {valid}")

        T_arr = np.atleast_1d(np.asarray(T, dtype=np.float64))

        # Warn on extrapolation
        below = T_arr < self.T_min
        above = T_arr > self.T_max
        if np.any(below):
            warnings.warn(
                f"Material '{self.name}': T={T_arr[below].tolist()} below data range "
                f"[{self.T_min:.1f}, {self.T_max:.1f}] K, clamping to nearest value.",
                stacklevel=3,
            )
        if np.any(above):
            warnings.warn(
                f"Material '{self.name}': T={T_arr[above].tolist()} above data range "
                f"[{self.T_min:.1f}, {self.T_max:.1f}] K, clamping to nearest value.",
                stacklevel=3,
            )

        # Warn on sparse data
        if self.n_points < 5:
            warnings.warn(
                f"Material '{self.name}' has only {self.n_points} data point(s). "
                f"Interpolation may be unreliable.",
                stacklevel=3,
            )

        if self.n_points == 1:
            result = np.full_like(T_arr, float(prop_map[property_name][0]))
        else:
            interp_func = PchipInterpolator(self.T, prop_map[property_name])
            T_clamped = np.clip(T_arr, self.T_min, self.T_max)
            result = interp_func(T_clamped)

        if np.isscalar(T) or (isinstance(T, np.ndarray) and T.ndim == 0):
            return float(result[0])
        return result
