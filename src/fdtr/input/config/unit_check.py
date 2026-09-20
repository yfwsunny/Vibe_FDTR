"""Lightweight unit-scale sanity checks for FDTR configs."""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class UnitCheckIssue:
    """A likely unit-scale issue found in a config value."""

    field: str
    value: object
    message: str

    def format(self) -> str:
        return f"unit sanity: {self.field}={self.value!r}: {self.message}"


class UnitCheckError(ValueError):
    """Raised when init-config receives values with likely unit mistakes."""


def emit_unit_check_issues(
    issues: Iterable[UnitCheckIssue],
    *,
    mode: str,
    stacklevel: int = 2,
) -> None:
    """Emit issues either as one error or as warnings."""
    issue_list = list(issues)
    if not issue_list:
        return
    if mode == "error":
        raise UnitCheckError("\n".join(issue.format() for issue in issue_list))
    if mode == "warning":
        for issue in issue_list:
            warnings.warn(issue.format(), UserWarning, stacklevel=stacklevel)
        return
    raise ValueError(f"Unknown unit check mode: {mode!r}")


def check_init_config_units(
    *,
    transducer_thickness: float | None = None,
    layer_thicknesses: Iterable[float | None] = (),
    spot_size: float | None = None,
    spot_x: float | None = None,
    spot_y: float | None = None,
    freq_offset: float | None = None,
    freq_spot: float | None = None,
    freq_ranges: Iterable[tuple[float, float]] | None = None,
    offset_ranges: Iterable[tuple[float, float]] | None = None,
    fit_params: dict[str, tuple[float, float]] | None = None,
    mode: str = "error",
) -> None:
    """Check init-config numeric inputs for likely unit mistakes."""
    issues: list[UnitCheckIssue] = []
    issues.extend(_spot_issues("spot_size", spot_size))
    issues.extend(_spot_issues("spot_x", spot_x))
    issues.extend(_spot_issues("spot_y", spot_y))
    issues.extend(_spot_average_issues("spot", spot_size, spot_x, spot_y))
    issues.extend(_thickness_issues("transducer thickness", transducer_thickness))
    for index, thickness in enumerate(layer_thicknesses):
        issues.extend(_thickness_issues(f"layer[{index}] thickness", thickness))
    issues.extend(_frequency_issues("freq_offset", freq_offset))
    issues.extend(_frequency_issues("freq_spot", freq_spot))
    issues.extend(_range_issues("freq_ranges", freq_ranges, _frequency_endpoint_issues))
    issues.extend(_range_issues("offset_ranges", offset_ranges, _offset_endpoint_issues))
    issues.extend(_named_fit_bounds_issues("fit", fit_params.items() if fit_params else ()))
    emit_unit_check_issues(issues, mode=mode, stacklevel=3)


def check_fit_config_units(config, *, mode: str = "warning") -> None:
    """Check a loaded FitConfig for likely unit mistakes."""
    issues: list[UnitCheckIssue] = []
    issues.extend(_spot_issues("fit.spot_size", getattr(config, "spot_size", None)))
    issues.extend(_spot_issues("fit.spot_x", getattr(config, "spot_x", None)))
    issues.extend(_spot_issues("fit.spot_y", getattr(config, "spot_y", None)))
    issues.extend(_spot_average_issues(
        "fit",
        getattr(config, "spot_size", None),
        getattr(config, "spot_x", None),
        getattr(config, "spot_y", None),
    ))
    issues.extend(_frequency_issues("fit.freq_offset", getattr(config, "freq_offset", None)))
    issues.extend(_frequency_issues("fit.freq_spot", getattr(config, "freq_spot", None)))
    issues.extend(_range_issues("fit.freq_ranges", getattr(config, "freq_ranges", None), _frequency_endpoint_issues))
    issues.extend(_range_issues("fit.offset_ranges", getattr(config, "offset_ranges", None), _offset_endpoint_issues))
    for index, layer in enumerate(getattr(config, "layers", [])):
        label = getattr(layer, "name", None) or getattr(layer, "material", None) or str(index)
        issues.extend(_thickness_issues(f"layer[{index}] {label} d", getattr(layer, "d", None)))
        for target in layer.to_targets(index):
            issues.extend(_fit_bounds_issues(f"fit bounds {target.name}", target.name, target.bounds))
    if getattr(config, "fit_spot_size", None) is not None:
        issues.extend(_fit_bounds_issues("fit bounds spot_size", "spot_size", config.fit_spot_size))
    if getattr(config, "fit_spot_x", None) is not None:
        issues.extend(_fit_bounds_issues("fit bounds spot_x", "spot_x", config.fit_spot_x))
    if getattr(config, "fit_spot_y", None) is not None:
        issues.extend(_fit_bounds_issues("fit bounds spot_y", "spot_y", config.fit_spot_y))
    for target in getattr(config, "targets", []):
        issues.extend(_fit_bounds_issues(f"fit bounds {target.name}", target.name, target.bounds))
    emit_unit_check_issues(issues, mode=mode, stacklevel=3)


def check_uncertainty_known_params(known_params: dict | None, *, mode: str = "warning") -> None:
    """Warn when relative uncertainty values look like absolute values."""
    if not known_params:
        return
    issues: list[UnitCheckIssue] = []
    for name, raw_value in known_params.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value != 0 and value < 0.001:
            issues.append(UnitCheckIssue(
                f"known_params.{name}",
                raw_value,
                "relative uncertainty is below 0.1%; values are fractions, e.g. 0.05 means 5%",
            ))
        elif value > 2.0:
            issues.append(UnitCheckIssue(
                f"known_params.{name}",
                raw_value,
                "relative uncertainty is above 200%; values are fractions, e.g. 0.05 means 5%",
            ))
    if issues:
        formatted = [
            UnitCheckIssue(issue.field, issue.value, f"relative uncertainty check: {issue.message}")
            for issue in issues
        ]
        emit_unit_check_issues(formatted, mode=mode, stacklevel=3)


def _spot_issues(field: str, value: float | None) -> list[UnitCheckIssue]:
    if value is None:
        return []
    value = float(value)
    if 0 < value < 1e-3:
        return [UnitCheckIssue(field, value, "spot values use micrometers; this looks like meters")]
    if value > 1000:
        return [UnitCheckIssue(field, value, "spot values use micrometers; value is unusually large")]
    return []


def _spot_average_issues(
    field: str,
    spot_size: float | None,
    spot_x: float | None,
    spot_y: float | None,
) -> list[UnitCheckIssue]:
    if spot_size is None or spot_x is None or spot_y is None:
        return []

    avg = (float(spot_x) + float(spot_y)) / 2.0
    if abs(float(spot_size) - avg) <= 1e-12:
        return []

    return [UnitCheckIssue(
        field,
        {"spot_size": spot_size, "spot_x": spot_x, "spot_y": spot_y},
        "spot_size must equal the average of spot_x and spot_y when all three are provided",
    )]


def _thickness_issues(field: str, value: float | None) -> list[UnitCheckIssue]:
    if value is None:
        return []
    value = float(value)
    if value > 1e-3 and value != 1:
        return [UnitCheckIssue(field, value, "thickness uses meters; use e.g. 48e-9 for 48 nm")]
    return []


def _frequency_issues(field: str, value: float | None) -> list[UnitCheckIssue]:
    if value is None:
        return []
    return _frequency_endpoint_issues(field, float(value))


def _frequency_endpoint_issues(field: str, value: float) -> list[UnitCheckIssue]:
    if 0 < value < 1e3:
        return [UnitCheckIssue(field, value, "frequency values use Hz; this looks like a MHz/kHz shorthand")]
    return []


def _offset_endpoint_issues(field: str, value: float) -> list[UnitCheckIssue]:
    abs_value = abs(float(value))
    if value != 0 and abs_value < 1e-3:
        return [UnitCheckIssue(field, value, "offset ranges use micrometers; this looks like meters")]
    if abs_value > 1e3:
        return [UnitCheckIssue(field, value, "offset ranges use micrometers; value is unusually large")]
    return []


def _range_issues(
    field: str,
    ranges: Iterable[tuple[float, float]] | None,
    endpoint_checker,
) -> list[UnitCheckIssue]:
    if ranges is None:
        return []
    issues: list[UnitCheckIssue] = []
    for i, (lo, hi) in enumerate(ranges):
        issues.extend(endpoint_checker(f"{field}[{i}].lo", float(lo)))
        issues.extend(endpoint_checker(f"{field}[{i}].hi", float(hi)))
    return issues


def _named_fit_bounds_issues(
    field_prefix: str,
    items: Iterable[tuple[str, tuple[float, float]]],
) -> list[UnitCheckIssue]:
    issues: list[UnitCheckIssue] = []
    for name, bounds in items:
        issues.extend(_fit_bounds_issues(f"{field_prefix}.{name}", name, bounds))
    return issues


def _fit_bounds_issues(
    field: str,
    name: str,
    bounds: tuple[float, float],
) -> list[UnitCheckIssue]:
    lo, hi = float(bounds[0]), float(bounds[1])
    issues: list[UnitCheckIssue] = []

    if not math.isfinite(lo) or not math.isfinite(hi):
        return [UnitCheckIssue(field, bounds, "fit bounds must be finite numbers")]
    if lo >= hi:
        issues.append(UnitCheckIssue(field, bounds, "fit bounds must satisfy lo < hi"))
    if lo <= 0 or hi <= 0:
        issues.append(UnitCheckIssue(field, bounds, "fit bounds for physical parameters must be positive"))

    endpoint_checker = _fit_bound_endpoint_checker(name)
    if endpoint_checker is not None:
        issues.extend(endpoint_checker(f"{field}.lo", lo))
        issues.extend(endpoint_checker(f"{field}.hi", hi))
    return issues


def _fit_bound_endpoint_checker(name: str):
    if name in {"spot_size", "spot_x", "spot_y"}:
        return _spot_issues
    if name.startswith("d_") or name == "d":
        return _thickness_bound_issues
    return None


def _thickness_bound_issues(field: str, value: float) -> list[UnitCheckIssue]:
    return _thickness_issues(field, value)
