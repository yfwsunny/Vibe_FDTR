"""Helpers for resolving config-origin paths at runtime."""

from __future__ import annotations

from pathlib import Path


def get_config_source_dir(config) -> Path | None:
    """Return the parent directory of the config source file, when known."""
    source_path = getattr(config, "source_path", None)
    if not source_path:
        return None
    return Path(source_path).resolve().parent


def resolve_config_path(config, value: str | Path | None) -> Path | None:
    """Resolve a path value relative to the config file location."""
    if value is None:
        return None

    path = Path(value)
    if path.is_absolute():
        return path.resolve()

    source_dir = get_config_source_dir(config)
    if source_dir is not None:
        return (source_dir / path).resolve()

    return path.resolve()
