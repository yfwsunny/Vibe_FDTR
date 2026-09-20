"""InitConfigRequest dataclass: input contract for init-config generation."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def parse_fit_param(name: str) -> tuple[str, int]:
    """Parse a fit parameter name into ``(property, layer_index)``."""
    if name in ("spot_size", "spot_x", "spot_y"):
        return (name, -1)

    parts = name.rsplit("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid fit parameter format: '{name}'")
    prop, idx_str = parts
    try:
        idx = int(idx_str)
    except ValueError as exc:
        raise ValueError(f"Invalid fit parameter format: '{name}'") from exc
    if idx < 0:
        raise ValueError(f"Invalid fit parameter format: '{name}'")
    return (prop, idx)


@dataclass
class InitConfigRequest:
    """Structured input for config generation."""

    transducer: str
    substrate: str
    strategy: str
    layers: list[str] = field(default_factory=list)
    transducer_thickness: float | None = None
    layer_thicknesses: list[float | None] = field(default_factory=list)
    temperature: float = 295.15

    fit_params: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Structured path input for the new init-config workflow.
    paths_spec: dict[str, Any] | None = None

    # Legacy/internal path fields remain available so existing builders/tests
    # can continue constructing requests directly.
    offset_dir: str | None = None
    offset_dir_y: str | None = None
    phase_dir: str | None = None
    data_file: str | None = None
    data_file_y: str | None = None
    offset_pattern: str | None = None
    offset_pattern_y: str | None = None
    phase_pattern: str | None = None
    offset_files: list[str] | None = None
    offset_files_y: list[str] | None = None
    phase_files: list[str] | None = None

    spot_size: float = 3.0
    spot_x: float | None = None
    spot_y: float | None = None
    freq_offset: float = 1.194e6
    freq_spot: float = 5.0e7
    signal: str = "phase"
    offset_points: int = 100
    phase_points: int = 80
    average: bool = True
    no_plot: bool = False
    freq_ranges: list[tuple[float, float]] | None = None
    offset_ranges: list[tuple[float, float]] | None = None

    pipeline: str | None = None
    iterations: int = 6

    output_dir: str | None = None
    report: bool = False
    full_template: bool = False

    @staticmethod
    def parse_fit_entries(entries: list[str]) -> dict[str, tuple[float, float]]:
        """Parse ``['Sr_2=100,10000', 'TBC_3=5e6,5e8']`` into a dict."""
        result: dict[str, tuple[float, float]] = {}
        for entry in entries:
            name, bounds_str = entry.split("=", 1)
            lo, hi = bounds_str.split(",", 1)
            result[name.strip()] = (float(lo.strip()), float(hi.strip()))
        return result

    @staticmethod
    def parse_material_spec(raw: str) -> tuple[str, float | None]:
        """Parse ``Material`` or ``Material:Thickness`` into name and thickness."""
        text = raw.strip()
        if not text:
            raise ValueError("Material name cannot be empty.")
        if ":" not in text:
            return (text, None)

        material, thickness_str = text.rsplit(":", 1)
        material = material.strip()
        thickness_str = thickness_str.strip()
        if not material:
            raise ValueError("Material name cannot be empty.")
        if not thickness_str:
            raise ValueError("Thickness cannot be empty.")
        try:
            thickness = float(thickness_str)
        except ValueError as exc:
            raise ValueError(f"Invalid thickness value: '{thickness_str}'") from exc
        return (material, thickness)

    @staticmethod
    def load_paths_spec_file(path: str | Path) -> dict[str, Any]:
        """Load a JSON or TOML path spec file."""
        spec_path = Path(path).resolve()
        if spec_path.suffix.lower() == ".json":
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        elif spec_path.suffix.lower() == ".toml":
            with spec_path.open("rb") as handle:
                spec = tomllib.load(handle)
        else:
            text = spec_path.read_text(encoding="utf-8")
            try:
                spec = json.loads(text)
            except json.JSONDecodeError:
                spec = tomllib.loads(text)

        if isinstance(spec, dict):
            spec["__source_path__"] = str(spec_path)
        return spec

    @staticmethod
    def load_paths_spec_json(text: str) -> dict[str, Any]:
        """Load an inline JSON path spec string."""
        return json.loads(text)
