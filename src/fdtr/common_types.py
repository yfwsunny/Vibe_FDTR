"""Shared type definitions used across FDTR layers.

These types define the contract between fitting engines and their consumers
(config, output, CLI). They have no dependency on any fdtr sub-package,
which breaks circular imports between input/fit/output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class SignalType(Enum):
    """Which signal channel the fitter compares against."""

    PHASE = "phase"
    AMPLITUDE = "amplitude"


@dataclass(frozen=True)
class FitTarget:
    """Description of one parameter to be fitted.

    Attributes:
        name: Parameter identifier (e.g. "S_z", "TBC").
        initial_guess: Starting value in *scaled* units (physical = guess * scale).
        bounds: (lower, upper) in scaled units.
        scale: Multiplicative factor to convert scaled -> physical units.
            Defaults to 1.0 (no scaling).
    """

    name: str
    initial_guess: float
    bounds: Tuple[float, float]
    scale: float = 1.0

    @property
    def physical_guess(self) -> float:
        """Initial guess in physical (unscaled) units."""
        return self.initial_guess * self.scale

    @property
    def physical_bounds(self) -> Tuple[float, float]:
        """Bounds in physical (unscaled) units."""
        return (self.bounds[0] * self.scale, self.bounds[1] * self.scale)


@dataclass(frozen=True)
class FitResult:
    """Outcome of a single fitting run.

    Attributes:
        fitted_values: Mapping of parameter name -> fitted physical value.
        residual: Sum of squares of the final residual vector.
        success: True if the optimiser converged.
        nfev: Number of function evaluations.
        message: Optimiser termination message.
    """

    fitted_values: Dict[str, float]
    residual: float
    success: bool
    nfev: int
    message: str = ""
    fitted_stack: Optional[Any] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict (excludes fitted_stack)."""
        return {
            "fitted_values": dict(self.fitted_values),
            "residual": float(self.residual),
            "success": self.success,
            "nfev": self.nfev,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FitResult":
        """Reconstruct a FitResult from a dict (fitted_stack is always None)."""
        return cls(
            fitted_values=d["fitted_values"],
            residual=d["residual"],
            success=d["success"],
            nfev=d["nfev"],
            message=d["message"],
            fitted_stack=None,
        )
