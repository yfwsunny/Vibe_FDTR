"""Dataclass definitions for FDTR configuration (field definitions only).

Business logic (TOML I/O, stack construction, target resolution) lives in the
sibling modules: ``config_io``, ``config_build``, ``config_from_args``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from fdtr.model.layer import (
    SYMMETRY_ISOTROPIC,
    SYMMETRY_TRANSVERSE,
    VALID_SYMMETRIES,
)


# ---------------------------------------------------------------------------
# Strategy normalization
# ---------------------------------------------------------------------------

_STRATEGY_ALIASES: dict[str, str] = {
    "freqfit": "freqfit",
    "offsetfit": "offsetfit",
    "spotfit": "spotfit",
    "iterfit": "iterfit",
}


def normalize_strategy(name: str) -> str:
    """Normalize a strategy name to its canonical form.

    Accepts ``freqfit``, ``offsetfit``, ``spotfit``, ``iterfit``.
    Unknown names are returned unchanged so custom strategies are preserved.
    """
    return _STRATEGY_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Helper dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerSpec:
    """Specification for a single layer in the config.

    Attributes:
        name: Human-readable layer name (e.g. "TBC").
        material: Material library name for auto-lookup (e.g. "Gold").
            When set, rho_cp/Sr/Sz are auto-filled from the library at config temperature.
            Explicit values (tracked in ``_explicit``) override library values.
        rho_cp: Volumetric heat capacity (J/m^3K). Zero for TBC interface layers.
        Sr: In-plane thermal conductivity (W/mK), or TBC conductance for TBC layers.
        Sz: Cross-plane thermal conductivity (W/mK), or TBC conductance for TBC layers.
        d: Thickness (m). Use 1.0 for TBC interface layers.
        fit_fields: Mapping of property name -> (lower, upper) bounds for fitting.
        _explicit: Set of property names explicitly set in TOML (overrides library).
    """

    name: str = ""
    material: str | None = None
    rho_cp: float = 0.0
    Sr: float = 1.0
    Sz: float = 1.0
    d: float = 1.0
    symmetry: str = SYMMETRY_TRANSVERSE
    fit_fields: dict[str, tuple[float, float]] = field(default_factory=dict, hash=False)
    _explicit: frozenset[str] = field(default_factory=frozenset, hash=False)

    def __post_init__(self) -> None:
        if self.symmetry not in VALID_SYMMETRIES:
            raise ValueError(
                f"Layer '{self.display_name or self.name}' has invalid symmetry "
                f"'{self.symmetry}'. Expected one of {sorted(VALID_SYMMETRIES)}."
            )
        if self.symmetry == SYMMETRY_ISOTROPIC and self.Sr != self.Sz:
            raise ValueError(
                f"Layer '{self.display_name or self.name}': isotropic symmetry "
                f"requires Sr == Sz (got Sr={self.Sr}, Sz={self.Sz})."
            )

    @property
    def is_tbc(self) -> bool:
        """True if this layer represents a TBC interface (rho_cp == 0 and no material)."""
        return self.material is None and self.rho_cp == 0.0

    @property
    def display_name(self) -> str:
        """Layer name for display: material name or explicit name."""
        return self.material or self.name

    def to_layer(self):
        """Convert to a core :class:`Layer` instance."""
        from fdtr.model.layer import Layer

        return Layer(
            rho_cp=self.rho_cp,
            Sr=self.Sr,
            Sz=self.Sz,
            d=self.d,
            name=self.display_name,
            symmetry=self.symmetry,
        )

    def to_targets(self, layer_index: int) -> list[TargetSpec]:
        """Convert fit_fields to TargetSpec list for this layer.

        ``fit_S`` on layer 2 -> ``TargetSpec(name="S_2", bounds=..., guess=(Sr+Sz)/2)``.
        ``fit_Sr`` on layer 2 -> ``TargetSpec(name="Sr_2", bounds=..., guess=self.Sr)``.
        ``fit_TBC`` on layer 1 -> ``TargetSpec(name="TBC_1", bounds=..., guess=self.Sr)``.
        """
        targets: list[TargetSpec] = []
        for prop, bounds in self.fit_fields.items():
            if prop == "TBC":
                targets.append(
                    TargetSpec(name=f"TBC_{layer_index}", bounds=bounds, guess=self.Sr)
                )
            elif prop == "S":
                targets.append(
                    TargetSpec(
                        name=f"S_{layer_index}",
                        bounds=bounds,
                        guess=(self.Sr + self.Sz) / 2.0,
                    )
                )
            else:
                guess = getattr(self, prop, None)
                targets.append(
                    TargetSpec(name=f"{prop}_{layer_index}", bounds=bounds, guess=guess)
                )
        return targets


@dataclass(frozen=True)
class TargetSpec:
    """Specification for one fit target parameter.

    Attributes:
        name: Parameter identifier. Supported formats:
            - ``"spot_size"`` -- pump+probe spot size
            - ``"TBC"`` -- thermal boundary conductance
            - ``"S_N"`` -- isotropic conductivity of layer N; fits Sr and Sz together
            - ``"Sr_N"`` -- in-plane conductivity of layer N
            - ``"Sz_N"`` -- cross-plane conductivity of layer N
            - ``"d_N"`` -- thickness of layer N
            - ``"rho_cp_N"`` -- volumetric heat capacity of layer N
            - ``"Sz_substrate"``, ``"Sr_substrate"`` -- backward-compat aliases
        bounds: (lower, upper) bounds for the parameter.
        guess: Optional initial guess. When ``None``, auto-resolved from layer values.
    """

    name: str
    bounds: Tuple[float, float]
    guess: Optional[float] = None

    @property
    def is_spot_size(self) -> bool:
        return self.name in ("spot_size", "spot_x", "spot_y")

    @property
    def is_tbc(self) -> bool:
        return self.name.startswith("TBC_") and self.name[4:].isdigit()

    @property
    def layer_index(self) -> int:
        """Extract the layer index from names like ``"Sr_2"`` or ``"TBC_1"``.

        Returns ``-1`` for ``spot_size`` and substrate aliases.
        """
        if self.is_spot_size:
            return -1
        if self.is_tbc:
            return int(self.name[4:])
        # Handle "sub_layer" suffix names -- resolved at runtime, not here
        if "_substrate" in self.name:
            return -1
        # Try to parse PROP_N pattern
        parts = self.name.rsplit("_", 1)
        if len(parts) == 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return -1

    @property
    def property_name(self) -> str:
        """Extract the property name from ``"Sr_2"`` -> ``"Sr"``.

        Returns ``""`` for ``spot_size`` and ``TBC_N``.
        """
        if self.is_spot_size or self.is_tbc:
            return ""
        if "_substrate" in self.name:
            return self.name.split("_")[0]  # "Sz_substrate" -> "Sz"
        parts = self.name.rsplit("_", 1)
        if len(parts) == 2:
            return parts[0]
        return ""


@dataclass(frozen=True)
class SensitivitySpec:
    parameters: List[str] = field(default_factory=lambda: ["all"])
    delta: float = 1e-4
    output_dir: Optional[str] = None


@dataclass(frozen=True)
class UncertaintySpec:
    known_params: Dict[str, float] = field(default_factory=dict)
    target_params: List[str] = field(default_factory=list)
    fit_result: Optional[str] = None
    full_output: bool = False


# ---------------------------------------------------------------------------
# Main config
# ---------------------------------------------------------------------------


@dataclass
class FitConfig:
    """Central configuration object for an FDTR fitting run.

    Construct manually or load from TOML via :func:`from_toml`.
    """

    temperature: float = 295.15
    layers: List[LayerSpec] = field(default_factory=list)
    offset_dir: Optional[str] = None
    phase_dir: Optional[str] = None
    data_file: Optional[str] = None
    data_file_y: Optional[str] = None
    offset_dir_y: Optional[str] = None
    strategy: str = "iterfit"
    iterations: int = 6
    sensitivity: Optional[SensitivitySpec] = None
    uncertainty: Optional[UncertaintySpec] = None
    targets: List[TargetSpec] = field(default_factory=list)
    freq_spot: float = 5.0e7
    freq_offset: float = 1.194e6
    offset_points: int = 100
    phase_points: int = 80
    average: bool = True
    spot_size: Optional[float] = None
    signal: str = "phase"
    freq_ranges: List[Tuple[float, float]] | None = None
    offset_ranges: list[tuple[float, float]] | None = None
    pipeline: str | None = None
    output_dir: Optional[str] = None

    # Data selection - glob patterns
    offset_pattern: Optional[str] = None
    offset_pattern_y: Optional[str] = None
    phase_pattern: Optional[str] = None

    # Data selection - explicit file lists
    offset_files: Optional[List[str]] = None
    offset_files_y: Optional[List[str]] = None
    phase_files: Optional[List[str]] = None

    # Spot-size fit bounds (new-style: fit_spot_size / fit_spot_x / fit_spot_y)
    fit_spot_size: Optional[Tuple[float, float]] = None
    fit_spot_x: Optional[Tuple[float, float]] = None
    fit_spot_y: Optional[Tuple[float, float]] = None
    group_key: Optional[str] = None
    source_path: Optional[str] = None
