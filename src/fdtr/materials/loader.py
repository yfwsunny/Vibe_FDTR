"""Material data file loader -- 4-column TXT with auto-detect headers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import numpy as np

from fdtr.materials.schema import Material, MaterialMetadata
from fdtr.model.layer import SYMMETRY_ISOTROPIC, SYMMETRY_TRANSVERSE

# Column name aliases for header auto-detection
COLUMN_ALIASES: dict[str, set[str]] = {
    "T": {"t(k)", "t (k)", "temperature", "t"},
    "rho_cp": {
        "rho_cp(j/m³k)", "rho_cp (j/m³k)", "c(j/m³k)", "c (j/m³k)",
        "rho_cp(j/m3k)", "rho_cp (j/m3k)", "c(j/m3k)", "c(j/m^3k)", "c (j/m^3k)",
        "rho_cp (j/m^3k)", "rho_cp",
    },
    "Sz": {"sz(w/mk)", "sz (w/mk)", "sz", "k_cross (w/mk)", "k_cross(w/mk)", "k_cross"},
    "Sr": {"sr(w/mk)", "sr (w/mk)", "sr"},
    "S": {"s(w/mk)", "s (w/mk)", "s"},
}

_BUILTIN_DATA_DIR = Path(__file__).resolve().parent / "data"


def _normalize_column_name(raw: str) -> str | None:
    normalized = raw.strip().lower()
    for std_name, aliases in COLUMN_ALIASES.items():
        if normalized in aliases:
            return std_name
    return None


def _split_line(line: str) -> list[str]:
    """Split a line by tab first, then by whitespace; strip each part."""
    parts = line.split("\t")
    if len(parts) < 3:
        parts = line.split()
    return [p.strip() for p in parts]


def _find_contiguous_header(parts: list[str]) -> dict[str, int] | None:
    """Find a contiguous run matching either isotropic or anisotropic columns."""
    if len(parts) < 3:
        return None
    for start in range(len(parts)):
        found: dict[str, int] = {}
        for j in range(start, len(parts)):
            std = _normalize_column_name(parts[j])
            if std is None:
                break
            found[std] = j
        keys = set(found)
        has_base = {"T", "rho_cp"} <= keys
        has_isotropic = "S" in keys and "Sr" not in keys and "Sz" not in keys
        has_anisotropic = {"Sr", "Sz"} <= keys and "S" not in keys
        if has_base and (has_isotropic or has_anisotropic):
            return found
    return None


def _parse_yaml_front_matter(lines: list[str]) -> tuple[MaterialMetadata | None, int]:
    """Extract YAML front-matter from lines, return (metadata, data_start_index)."""
    if not lines or lines[0].strip() != "---":
        return None, 0

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, 0

    meta = MaterialMetadata()
    for line in lines[1:end_idx]:
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key == "source":
            meta = MaterialMetadata(
                source=value, author=meta.author, date=meta.date, notes=meta.notes,
            )
        elif key == "author":
            meta = MaterialMetadata(
                source=meta.source, author=value, date=meta.date, notes=meta.notes,
            )
        elif key == "date":
            meta = MaterialMetadata(
                source=meta.source, author=meta.author, date=value, notes=meta.notes,
            )
        elif key == "notes":
            meta = MaterialMetadata(
                source=meta.source, author=meta.author, date=meta.date, notes=value,
            )

    return meta, end_idx + 1


def _detect_header_and_data(lines: list[str], start: int = 0) -> tuple[dict[str, int], int]:
    """Find the header line and return column mapping + data start index."""
    for i in range(start, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = _split_line(line)
        if len(parts) < 3:
            continue
        found = _find_contiguous_header(parts)
        if found is not None:
            return found, i + 1
    raise ValueError("No valid header line found in material file")


def _parse_row(
    parts: list[str],
    column_map: dict[str, int],
    is_isotropic: bool,
) -> tuple[float, float, float, float]:
    """Parse one data row as (T, rho_cp, Sz, Sr)."""
    T = float(parts[column_map["T"]])
    rho_cp = float(parts[column_map["rho_cp"]])
    if is_isotropic:
        s_val = float(parts[column_map["S"]])
        return T, rho_cp, s_val, s_val
    Sz = float(parts[column_map["Sz"]])
    Sr = float(parts[column_map["Sr"]])
    return T, rho_cp, Sz, Sr


def load_material(filepath: Path | str) -> Material:
    """Load a material from a 4-column TXT file.

    Expected columns: T(K), rho_cp(J/m³K), Sz(W/mK), Sr(W/mK).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Material file not found: {filepath}")
    name = filepath.stem
    raw = filepath.read_text(encoding="utf-8")
    lines = raw.strip().splitlines()
    if not lines:
        raise ValueError(f"No data in material file: {filepath}")

    # Parse optional YAML front-matter
    metadata, content_start = _parse_yaml_front_matter(lines)

    # Find header and data
    column_map, data_start = _detect_header_and_data(lines, start=content_start)
    is_isotropic = "S" in column_map

    T_rows: list[float] = []
    rho_cp_rows: list[float] = []
    Sz_rows: list[float] = []
    Sr_rows: list[float] = []

    # Check if the header line also contains data values after the header columns
    header_line = lines[data_start - 1].strip()
    header_parts = _split_line(header_line)
    header_end = max(column_map.values()) + 1
    ncols = 3 if is_isotropic else 4
    if len(header_parts) >= header_end + ncols:
        try:
            inline_parts = header_parts[header_end:header_end + ncols]
            rel_map = {"T": 0, "rho_cp": 1, "S": 2} if is_isotropic else {
                "T": 0,
                "rho_cp": 1,
                "Sz": 2,
                "Sr": 3,
            }
            T, rho_cp, Sz, Sr = _parse_row(inline_parts, rel_map, is_isotropic)
            T_rows.append(T)
            rho_cp_rows.append(rho_cp)
            Sz_rows.append(Sz)
            Sr_rows.append(Sr)
        except (ValueError, IndexError):
            pass

    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = _split_line(line)
        if len(parts) < ncols:
            continue
        try:
            T, rho_cp, Sz, Sr = _parse_row(parts, column_map, is_isotropic)
            T_rows.append(T)
            rho_cp_rows.append(rho_cp)
            Sz_rows.append(Sz)
            Sr_rows.append(Sr)
        except (ValueError, IndexError):
            continue

    if len(T_rows) < 1:
        raise ValueError(f"No data in material file: {filepath}")

    return Material(
        name=name,
        T=np.array(T_rows),
        rho_cp=np.array(rho_cp_rows),
        Sz=np.array(Sz_rows),
        Sr=np.array(Sr_rows),
        symmetry=SYMMETRY_ISOTROPIC if is_isotropic else SYMMETRY_TRANSVERSE,
        metadata=metadata,
    )


def resolve_material(name: str) -> Material:
    """Load a built-in material from the package data directory.

    Args:
        name: Material name (e.g. "Gold", "Graphite"). Must not contain path separators.

    Returns:
        Material instance.

    Raises:
        ValueError: If name contains path separators.
        FileNotFoundError: If no matching data file is found.
    """
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"Invalid material name: {name!r}")

    # Exact match first
    exact = _BUILTIN_DATA_DIR / f"{name}.txt"
    if exact.exists():
        return load_material(exact)

    # Case-insensitive match
    for candidate in _BUILTIN_DATA_DIR.glob("*.txt"):
        if candidate.stem.lower() == name.lower():
            return load_material(candidate)

    # Prefix match (for variants like Gold_58nm)
    candidates = list(_BUILTIN_DATA_DIR.glob(f"{name}*.txt"))
    if candidates:
        return load_material(candidates[0])

    available = sorted(p.stem for p in _BUILTIN_DATA_DIR.glob("*.txt"))
    raise FileNotFoundError(
        f"Material '{name}' not found. Available: {available}"
    )


def try_resolve_material(name: str):
    """Resolve material, returning None if not found instead of raising."""
    try:
        return resolve_material(name)
    except FileNotFoundError:
        return None


def load_materials_dir(dirpath: Path | str) -> dict[str, Material]:
    """Load all .txt material files from a directory."""
    dirpath = Path(dirpath)
    if not dirpath.exists():
        raise FileNotFoundError(f"Materials directory not found: {dirpath}")
    materials: dict[str, Material] = {}
    for filepath in sorted(dirpath.glob("*.txt")):
        try:
            mat = load_material(filepath)
            materials[mat.name] = mat
        except Exception as e:
            import warnings
            warnings.warn(f"Skipping material file {filepath.name}: {e}", stacklevel=2)
    return materials
