"""Layer and MultilayerStack data models for the H2D thermal model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

SYMMETRY_ISOTROPIC = "isotropic"
SYMMETRY_TRANSVERSE = "transverse_isotropic"
VALID_SYMMETRIES = frozenset({SYMMETRY_ISOTROPIC, SYMMETRY_TRANSVERSE})


@dataclass(frozen=True)
class Layer:
    """A single layer in the multilayer thermal stack."""

    rho_cp: float
    Sr: float
    Sz: float
    d: float
    name: str = ""
    symmetry: str = SYMMETRY_TRANSVERSE

    def __post_init__(self) -> None:
        if self.symmetry not in VALID_SYMMETRIES:
            raise ValueError(
                f"Layer '{self.name}' has invalid symmetry '{self.symmetry}'. "
                f"Expected one of {sorted(VALID_SYMMETRIES)}."
            )
        if self.symmetry == SYMMETRY_ISOTROPIC and self.Sr != self.Sz:
            raise ValueError(
                f"Layer '{self.name}': isotropic symmetry requires Sr == Sz "
                f"(got Sr={self.Sr}, Sz={self.Sz})."
            )

    @property
    def is_tbc(self) -> bool:
        """True if this layer represents a thermal boundary conductance interface."""
        return self.rho_cp == 0.0

    @property
    def thermal_resistance(self) -> float:
        """Thermal resistance R = d / Sz. Only valid for TBC layers."""
        if not self.is_tbc:
            raise ValueError(
                "thermal_resistance is only defined for TBC layers (rho_cp == 0). "
                f"Layer '{self.name}' has rho_cp = {self.rho_cp}."
            )
        return self.d / self.Sz

    def to_vector(self) -> np.ndarray:
        """Return [rho_cp, Sr, Sz, d] as a 1-D numpy array."""
        return np.array([self.rho_cp, self.Sr, self.Sz, self.d])


class MultilayerStack:
    """Ordered stack of layers from top surface (index 0) to substrate."""

    def __init__(self, layers: List[Layer]) -> None:
        if not layers:
            raise ValueError("MultilayerStack must contain at least one layer.")
        self.layers: List[Layer] = list(layers)

    @property
    def num_layers(self) -> int:
        return len(self.layers)

    def __len__(self) -> int:
        return self.num_layers

    @property
    def rho_cp(self) -> np.ndarray:
        return np.array([l.rho_cp for l in self.layers])

    @property
    def Sr(self) -> np.ndarray:
        return np.array([l.Sr for l in self.layers])

    @property
    def Sz(self) -> np.ndarray:
        return np.array([l.Sz for l in self.layers])

    @property
    def d(self) -> np.ndarray:
        return np.array([l.d for l in self.layers])

    @property
    def substrate_index(self) -> int:
        """Index of the last non-TBC layer (the substrate)."""
        for i in range(len(self.layers) - 1, -1, -1):
            if not self.layers[i].is_tbc:
                return i
        raise ValueError("No non-TBC layer found in the stack.")
