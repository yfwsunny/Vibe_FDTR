"""Configuration module for FDTR toolkit.

Re-exports the most commonly used names so callers can write::

    from fdtr.input.config import FitConfig, from_toml, to_toml, to_stack
"""

# Dataclasses & normalization
from fdtr.input.config.config_dataclass import (
    FitConfig,
    LayerSpec,
    SensitivitySpec,
    TargetSpec,
    UncertaintySpec,
    normalize_strategy,
)

# TOML I/O
from fdtr.input.config.config_io import (
    from_toml,
    to_toml,
)

# Stack / target / guess construction
from fdtr.input.config.config_build import (
    apply_fit_fields,
    build_layers_from_materials,
    collect_all_target_names,
    resolve_guess,
    resolve_material_properties,
    to_fit_targets,
    to_stack,
)

# Template generation
from fdtr.input.config.config_template import (
    build_fit_config,
)

# Flat analysis config loader
from fdtr.input.config.analysis_config import (
    load_analysis_config,
)

__all__ = [
    "FitConfig",
    "LayerSpec",
    "SensitivitySpec",
    "TargetSpec",
    "UncertaintySpec",
    "apply_fit_fields",
    "build_layers_from_materials",
    "collect_all_target_names",
    "from_toml",
    "normalize_strategy",
    "resolve_guess",
    "resolve_material_properties",
    "to_fit_targets",
    "to_stack",
    "load_analysis_config",
    "to_toml",
]
