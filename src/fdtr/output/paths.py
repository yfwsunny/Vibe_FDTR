"""Unified output directory resolution for FDTR toolkit."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import tomllib
from typing import Optional


def resolve_output_dir(
    output_dir: Optional[str],
    config_path: Optional[Path] = None,
    *,
    material_names: Optional[list[str]] = None,
) -> Path:
    """Resolve the unified output directory.

    Priority:
      1. output_dir is absolute path -> use directly
      2. output_dir is relative + config_path given -> resolve relative to config parent
      3. output_dir is None -> auto-generate under tasks/

    Returns created Path.
    """
    if output_dir is not None:
        path = Path(output_dir)
        if not path.is_absolute() and config_path is not None:
            path = config_path.resolve().parent / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    # No explicit output_dir: if using a config file, output next to it
    if config_path is not None:
        path = config_path.resolve().parent
        path.mkdir(parents=True, exist_ok=True)
        return path

    return _auto_output_dir(material_names)


def _find_project_root(start: Path) -> Path:
    """Walk upward from *start* to find the directory containing pyproject.toml."""
    candidate = start.resolve()
    for _ in range(20):
        if (candidate / "pyproject.toml").exists():
            return candidate
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return start.resolve()


def _auto_output_dir(
    material_names: Optional[list[str]] = None,
    config_path: Optional[Path] = None,
) -> Path:
    """Create a date-level session directory under tasks/."""
    ts = datetime.now().strftime("%Y%m%d")
    suffix = ""
    if material_names:
        suffix = "_" + "_".join(material_names)
    base_stem = f"{ts}{suffix}"

    if config_path is not None:
        root = _find_project_root(config_path.resolve().parent)
    else:
        root = _find_project_root(Path.cwd())

    tasks = root / "tasks"
    candidate = tasks / base_stem
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    counter = 2
    while True:
        candidate = tasks / f"{base_stem}_{counter}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        counter += 1


def find_task_root(path: str | Path | None) -> Path | None:
    """Return the enclosing ``tasks/<session>`` directory for *path*, if any."""
    if path is None:
        return None

    candidate = Path(path).resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for current in (candidate, *candidate.parents):
        if current.parent.name == "tasks":
            return current
    return None


def resolve_task_root(
    *,
    explicit_output: str | Path | None = None,
    inherited_from: str | Path | None = None,
    material_names: Optional[list[str]] = None,
    group_key: str | None = None,
    config_path: Optional[Path] = None,
) -> Path:
    """Resolve the task/session root for newly generated artifacts."""
    if explicit_output is not None:
        explicit_path = Path(explicit_output).resolve()
        inherited = find_task_root(explicit_path)
        return inherited or explicit_path.parent

    inherited = find_task_root(inherited_from)
    if inherited is not None:
        return inherited

    auto_names = [group_key] if group_key else material_names
    return _auto_output_dir(auto_names, config_path=config_path)


def _slugify(value: str | None) -> str:
    """Normalize arbitrary text into a filesystem-friendly identifier."""
    if not value:
        return ""
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.strip()).strip("_").lower()
    return slug


def get_material_names(config) -> list[str]:
    """Extract material names excluding the transducer (layer 0).

    Returns the first and last non-TBC material after skipping the transducer.
    For Au/graphite/sapphire this returns [Graphite, Sapphire].
    """
    names = []
    for layer in config.layers:
        mat = getattr(layer, "material", None) or getattr(layer, "name", None)
        if mat:
            # Skip TBC interface layers (rho_cp == 0)
            rho_cp = getattr(layer, "rho_cp", None)
            if rho_cp is not None and rho_cp == 0:
                continue
            names.append(mat)
    # Skip transducer (index 0), take first and last of remaining
    inner = names[1:] if len(names) > 1 else names
    if len(inner) >= 2:
        return [inner[0], inner[-1]]
    return inner


def get_material_names_from_dict(config_dict: dict) -> list[str]:
    """Extract material names excluding the transducer from a raw TOML config dict."""
    names = []
    for layer in config_dict.get("layer", []):
        mat = layer.get("material") or layer.get("name")
        if mat and layer.get("rho_cp", 1.0) != 0.0:
            names.append(mat)
    # Skip transducer (index 0), take first and last of remaining
    inner = names[1:] if len(names) > 1 else names
    if len(inner) >= 2:
        return [inner[0], inner[-1]]
    return inner


def derive_group_slug(
    *,
    group_key: str | None = None,
    material_names: Optional[list[str]] = None,
    fallback_path: str | Path | None = None,
) -> str:
    """Resolve a stable group slug for automatic artifact naming."""
    slug = _slugify(group_key)
    if slug:
        return slug

    if material_names:
        parts = [_slugify(name) for name in material_names if _slugify(name)]
        if parts:
            return "_".join(parts)

    if fallback_path is not None:
        fallback = Path(fallback_path)
        stem = fallback.stem if fallback.suffix else fallback.name
        slug = _slugify(stem)
        if slug:
            return slug

    return "fdtr"


def _strip_known_prefix(stem: str) -> str:
    """Remove leading artifact prefixes when they carry no grouping information."""
    patterns = (
        r"^config_(?:freq|offset|spot|iter)_(.+)$",
        r"^fit_result_(?:freq|offset|spot|iter)_(.+)$",
        r"^report_(?:freq|offset|spot|iter)_(.+)$",
        r"^(?:freq|offset|spot|iter)fit_.+?_(.+)$",
        r"^(?:freq|offset)_(?:phase|amplitude)_sensitivity_(.+)$",
        r"^uncertainty_result_(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, stem)
        if match:
            return match.group(1)
    return stem


def derive_group_slug_from_config(config_path: Path | None) -> str:
    """Recover the preferred group slug from a config file or its filename."""
    if config_path is None:
        return "fdtr"

    path = Path(config_path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        raw = {}

    group_key = raw.get("paths", {}).get("group_key")

    if group_key is None and "base_config" in raw:
        base = path.resolve().parent / raw["base_config"]
        if base.is_file():
            return derive_group_slug_from_config(base)

    material_names = get_material_names_from_dict(raw) if raw else None
    fallback = _strip_known_prefix(path.stem)
    return derive_group_slug(
        group_key=group_key,
        material_names=material_names,
        fallback_path=fallback,
    )


def derive_group_slug_from_artifact(path: Path | None) -> str:
    """Recover the group slug from an existing artifact filename."""
    if path is None:
        return "fdtr"
    stem = _strip_known_prefix(Path(path).stem)
    return derive_group_slug(fallback_path=stem)


def _next_available_path(path: Path) -> Path:
    """Return *path* or the next numbered sibling that does not already exist."""
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


@dataclass
class OutputPaths:
    """Central naming registry for all FDTR output files."""
    base: Path       # task root directory
    command: str     # freq | offset | spot | iter
    suffix: str = "" # group identifier derived from config filename

    def _with_suffix(self, stem: str, extension: str, suffix: str = "") -> Path:
        s = suffix or self.suffix
        if s:
            stem += f"_{s}"
        return self.base / f"{stem}{extension}"

    def _next(self, path: Path) -> Path:
        self.base.mkdir(parents=True, exist_ok=True)
        return _next_available_path(path)

    def fit_result(self, suffix: str = "") -> Path:
        return self._with_suffix(f"fit_result_{self.command}", ".json", suffix)

    def report(self, suffix: str = "") -> Path:
        return self._with_suffix(f"report_{self.command}", ".md", suffix)

    def plot(self, name: str, suffix: str = "") -> Path:
        return self._with_suffix(f"{self.command}fit_{name}", ".png", suffix)

    def sensitivity_csv(self, mode: str, signal: str, suffix: str = "") -> Path:
        return self._with_suffix(f"{mode}_{signal}_sensitivity", ".csv", suffix)

    def sensitivity_plot(self, mode: str, signal: str, suffix: str = "") -> Path:
        return self._with_suffix(f"{mode}_{signal}_sensitivity", ".png", suffix)

    def config(self, suffix: str = "") -> Path:
        return self._with_suffix(f"config_{self.command}", ".toml", suffix)

    def uncertainty_result(self, suffix: str = "") -> Path:
        return self._with_suffix("uncertainty_result", ".json", suffix)

    def pipeline(self, suffix: str = "") -> Path:
        return self._with_suffix("pipeline", ".toml", suffix)

    def fit_csv(self, name: str, suffix: str = "") -> Path:
        return self._with_suffix(f"{self.command}fit_{name}", ".csv", suffix)

    def next_fit_csv_path(self, name: str, suffix: str = "") -> Path:
        return self._next(self.fit_csv(name, suffix))

    def summary(self, suffix: str = "") -> Path:
        return self._with_suffix("summary", ".md", suffix)

    def next_summary_path(self, suffix: str = "") -> Path:
        return self._next(self.summary(suffix))

    def next_fit_result_path(self, suffix: str = "") -> Path:
        return self._next(self.fit_result(suffix))

    def next_report_path(self, suffix: str = "") -> Path:
        return self._next(self.report(suffix))

    def next_plot_path(self, name: str, suffix: str = "") -> Path:
        return self._next(self.plot(name, suffix))

    def next_sensitivity_csv_path(self, mode: str, signal: str, suffix: str = "") -> Path:
        return self._next(self.sensitivity_csv(mode, signal, suffix))

    def next_sensitivity_plot_path(self, mode: str, signal: str, suffix: str = "") -> Path:
        return self._next(self.sensitivity_plot(mode, signal, suffix))

    def next_config_path(self, suffix: str = "") -> Path:
        return self._next(self.config(suffix))

    def next_uncertainty_result_path(self, suffix: str = "") -> Path:
        return self._next(self.uncertainty_result(suffix))

    def next_pipeline_path(self, suffix: str = "") -> Path:
        return self._next(self.pipeline(suffix))
