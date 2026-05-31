"""Small helpers for spot-size policy at config boundaries."""

from __future__ import annotations

from fdtr.input.config.config_dataclass import FitConfig


def require_scalar_spot_size(config: FitConfig, context: str) -> float:
    """Return ``spot_size`` for workflows that use a scalar spot.

    Direction-specific ``spot_x`` / ``spot_y`` values are intentionally not
    promoted here. They are only meaningful for iterfit pipeline ``spot_key``
    handling and directional spotfit.
    """
    if config.spot_size is not None:
        return float(config.spot_size)

    directional = [
        name
        for name, value in (("spot_x", config.spot_x), ("spot_y", config.spot_y))
        if value is not None
    ]
    if directional:
        fields = ", ".join(directional)
        raise ValueError(
            f"{context} requires [fit] spot_size. Found {fields}, but "
            "directional spot fields are only used by iterfit pipeline "
            "spot_key steps or directional spotfit."
        )

    raise ValueError(f"{context} requires [fit] spot_size.")


def average_directional_spots(
    spot_x: float | None,
    spot_y: float | None,
) -> float | None:
    """Return an average scalar spot from optional directional values."""
    if spot_x is not None and spot_y is not None:
        return (float(spot_x) + float(spot_y)) / 2.0
    if spot_x is not None:
        return float(spot_x)
    if spot_y is not None:
        return float(spot_y)
    return None


def ignored_directional_spot_warning(config: FitConfig, context: str) -> str | None:
    """Return a warning if scalar workflows receive directional spot fields."""
    directional = [
        name
        for name, value in (("spot_x", config.spot_x), ("spot_y", config.spot_y))
        if value is not None
    ]
    if not directional:
        return None
    fields = ", ".join(directional)
    return (
        f"{context} uses [fit] spot_size; {fields} are ignored. Use iterfit "
        "pipeline spot_key or directional spotfit when X/Y spots are required."
    )
