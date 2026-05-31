"""Stack construction, target resolution, and material-property resolution."""

from __future__ import annotations

import dataclasses
import warnings
from typing import List

from fdtr.input.config.config_dataclass import (
    FitConfig,
    LayerSpec,
    TargetSpec,
)
from fdtr.model.layer import SYMMETRY_ISOTROPIC, SYMMETRY_TRANSVERSE


# ---------------------------------------------------------------------------
# Layer stack from material names
# ---------------------------------------------------------------------------


def build_layers_from_materials(
    transducer: str | None = None,
    substrate: str | None = None,
    intermediate: list[str] | None = None,
    transducer_thickness: float | None = None,
    layer_thicknesses: list[float | None] | None = None,
    temperature: float = 295.15,
) -> list[LayerSpec]:
    """Build a layer stack from material library names with auto-inserted TBC interfaces.

    Args:
        transducer: Material name for transducer (default d=48e-9).
        substrate: Material name for substrate (default d=1.0, semi-infinite).
        intermediate: Optional intermediate material names (default d=100e-9 each).
        transducer_thickness: Optional explicit transducer thickness in meters.
        layer_thicknesses: Optional per-intermediate thicknesses in meters.
        temperature: Temperature in Kelvin for material property lookup.
    """
    import sys

    from fdtr.materials.loader import try_resolve_material

    intermediate = intermediate or []
    layer_thicknesses = layer_thicknesses or []
    material_specs: list[LayerSpec] = []
    transducer_d = 48e-9 if transducer_thickness is None else transducer_thickness

    # Transducer
    if transducer is not None:
        mat = try_resolve_material(transducer)
        if mat is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rho_cp = float(mat.get_property_at_T(temperature, "rho_cp"))
                Sr = float(mat.get_property_at_T(temperature, "Sr"))
                Sz = float(mat.get_property_at_T(temperature, "Sz"))
            material_specs.append(LayerSpec(material=transducer, rho_cp=rho_cp, Sr=Sr, Sz=Sz, d=transducer_d, symmetry=mat.symmetry))
        else:
            print(f"WARNING: Material '{transducer}' not found. Placeholder values.", file=sys.stderr)
            material_specs.append(LayerSpec(name=transducer, rho_cp=-1.0, Sr=-1.0, Sz=-1.0, d=transducer_d))
    else:
        material_specs.append(
            LayerSpec(
                name="Gold",
                rho_cp=2.48e6,
                Sr=140.0,
                Sz=140.0,
                d=transducer_d,
                symmetry=SYMMETRY_ISOTROPIC,
            )
        )

    # Intermediate layers
    for idx, mat_name in enumerate(intermediate):
        layer_d = layer_thicknesses[idx] if idx < len(layer_thicknesses) and layer_thicknesses[idx] is not None else 100e-9
        mat = try_resolve_material(mat_name)
        if mat is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rho_cp = float(mat.get_property_at_T(temperature, "rho_cp"))
                Sr = float(mat.get_property_at_T(temperature, "Sr"))
                Sz = float(mat.get_property_at_T(temperature, "Sz"))
            material_specs.append(LayerSpec(material=mat_name, rho_cp=rho_cp, Sr=Sr, Sz=Sz, d=layer_d, symmetry=mat.symmetry))
        else:
            print(f"WARNING: Material '{mat_name}' not found. Placeholder values.", file=sys.stderr)
            material_specs.append(LayerSpec(name=mat_name, rho_cp=-1.0, Sr=-1.0, Sz=-1.0, d=layer_d))

    # Substrate
    if substrate is not None:
        mat = try_resolve_material(substrate)
        if mat is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rho_cp = float(mat.get_property_at_T(temperature, "rho_cp"))
                Sr = float(mat.get_property_at_T(temperature, "Sr"))
                Sz = float(mat.get_property_at_T(temperature, "Sz"))
            material_specs.append(LayerSpec(material=substrate, rho_cp=rho_cp, Sr=Sr, Sz=Sz, d=1.0, symmetry=mat.symmetry))
        else:
            print(f"WARNING: Material '{substrate}' not found. Placeholder values.", file=sys.stderr)
            material_specs.append(LayerSpec(name=substrate, rho_cp=-1.0, Sr=-1.0, Sz=-1.0, d=1.0))
    else:
        material_specs.append(LayerSpec(name="Substrate", rho_cp=1.62e6, Sr=1860.0, Sz=6.0, d=1.0))

    # Insert TBC interfaces between each pair
    layers: list[LayerSpec] = []
    for i, spec in enumerate(material_specs):
        layers.append(spec)
        if i < len(material_specs) - 1:
            layers.append(LayerSpec(name="TBC", rho_cp=0.0, Sr=5.0e7, Sz=5.0e7, d=1.0))

    return layers


# ---------------------------------------------------------------------------
# Strategy-dependent fit field application
# ---------------------------------------------------------------------------


def apply_fit_fields(
    config: FitConfig,
    strategy: str,
    fit_params: dict[str, tuple[float, float]] | None = None,
) -> None:
    """Apply strategy-default fit bounds then override with indexed fit_params."""
    from fdtr.input.config.config_request import parse_fit_param

    fit_params = fit_params or {}
    layers = config.layers

    # Collect spot-level overrides before strategy defaults
    spot_overrides: dict[str, tuple[float, float]] = {}
    layer_overrides: dict[int, dict[str, tuple[float, float]]] = {}

    for key, bounds in fit_params.items():
        prop, idx = parse_fit_param(key)
        if idx == -1:
            spot_overrides[prop] = bounds
        else:
            if idx >= len(layers):
                raise ValueError(
                    f"Fit parameter '{key}' references layer {idx}, "
                    f"but config has only {len(layers)} layers (0..{len(layers) - 1})."
                )
            layer = layers[idx]
            if layer.is_tbc and prop != "TBC":
                raise ValueError(f"{key}: TBC layer; use fit_TBC/TBC_{idx} instead.")
            if not layer.is_tbc and layer.symmetry == SYMMETRY_ISOTROPIC and prop in {"Sr", "Sz"}:
                raise ValueError(f"{key}: layer uses S; use fit_S/S_{idx} instead.")
            if not layer.is_tbc and layer.symmetry != SYMMETRY_ISOTROPIC and prop == "S":
                raise ValueError(f"{key}: layer uses Sr/Sz; use fit_Sr/fit_Sz instead.")
            layer_overrides.setdefault(idx, {})[prop] = bounds

    # Strategy defaults
    substrate_fit: dict[str, tuple[float, float]] = {}
    tbc_fit: dict[str, tuple[float, float]] = {}

    if strategy == "spotfit":
        if "spot_size" not in spot_overrides:
            config.fit_spot_size = (0.3, 30.0)

    elif strategy == "offsetfit":
        sub_idx = _find_last_non_tbc(layers)
        if sub_idx is not None and layers[sub_idx].symmetry == SYMMETRY_ISOTROPIC:
            substrate_fit["S"] = (100.0, 10000.0)
        else:
            substrate_fit["Sr"] = (100.0, 10000.0)

    elif strategy == "freqfit":
        sub_idx = _find_last_non_tbc(layers)
        if sub_idx is not None and layers[sub_idx].symmetry == SYMMETRY_ISOTROPIC:
            substrate_fit["S"] = (0.6, 60.0)
        else:
            substrate_fit["Sz"] = (0.6, 60.0)
        tbc_fit["TBC"] = (5e6, 5e8)

    elif strategy == "iterfit":
        if "spot_x" not in spot_overrides:
            config.fit_spot_x = (0.3, 30.0)
        if "spot_y" not in spot_overrides:
            config.fit_spot_y = (0.3, 30.0)
        sub_idx = _find_last_non_tbc(layers)
        if sub_idx is not None and layers[sub_idx].symmetry == SYMMETRY_ISOTROPIC:
            substrate_fit["S"] = (100.0, 10000.0)
        else:
            substrate_fit["Sr"] = (100.0, 10000.0)
            substrate_fit["Sz"] = (0.6, 60.0)
        tbc_fit["TBC"] = (5e6, 5e8)
        if config.pipeline is None:
            config.pipeline = "builtin:default"

    # Apply spot overrides
    for prop, bounds in spot_overrides.items():
        if prop == "spot_size":
            config.fit_spot_size = bounds
        elif prop == "spot_x":
            config.fit_spot_x = bounds
        elif prop == "spot_y":
            config.fit_spot_y = bounds

    # Apply TBC fit fields (only to TBC layers with indexed overrides)
    tbc_override_indices = {i for i in layer_overrides if layers[i].is_tbc}
    if tbc_fit and not tbc_override_indices:
        # No explicit TBC overrides: apply defaults to all TBC layers
        tbc_override_indices = {i for i, l in enumerate(layers) if l.is_tbc}
    if tbc_override_indices:
        new_layers = []
        for i, layer in enumerate(layers):
            if layer.is_tbc and i in tbc_override_indices:
                override = layer_overrides.get(i, {})
                merged = dict(tbc_fit)
                merged.update(override)
                new_layers.append(dataclasses.replace(layer, fit_fields=merged))
            else:
                new_layers.append(layer)
        config.layers = new_layers

    # Apply substrate fit fields (strategy defaults on last non-TBC layer)
    if substrate_fit:
        sub_idx = _find_last_non_tbc(config.layers)
        if sub_idx is not None:
            override = layer_overrides.get(sub_idx, {})
            # Skip strategy defaults for properties that intermediate layers override
            has_intermediate_override = any(
                i != sub_idx for i in layer_overrides
            )
            if has_intermediate_override:
                # Don't apply substrate strategy defaults at all when intermediate
                # layers are explicitly targeted via fit_params
                if override:
                    sub = config.layers[sub_idx]
                    config.layers[sub_idx] = dataclasses.replace(sub, fit_fields=override)
            else:
                merged = dict(substrate_fit)
                merged.update(override)
                sub = config.layers[sub_idx]
                config.layers[sub_idx] = dataclasses.replace(sub, fit_fields=merged)

    # Apply remaining indexed overrides for intermediate layers
    sub_idx = _find_last_non_tbc(config.layers)
    for idx, overrides in layer_overrides.items():
        layer = config.layers[idx]
        if idx != sub_idx or not substrate_fit:
            merged = {**layer.fit_fields, **overrides}
            config.layers[idx] = dataclasses.replace(layer, fit_fields=merged)


def _find_last_non_tbc(layers: list) -> int | None:
    for i in range(len(layers) - 1, -1, -1):
        if not layers[i].is_tbc:
            return i
    return None


# ---------------------------------------------------------------------------
# Stack construction
# ---------------------------------------------------------------------------


def to_stack(config: FitConfig):
    """Build a :class:`MultilayerStack` from the layer specifications."""
    from fdtr.model.layer import MultilayerStack

    if not config.layers:
        raise ValueError("FitConfig has no layers defined.")
    resolved = [resolve_material_properties(config, ls).to_layer() for ls in config.layers]
    return MultilayerStack(resolved)


# ---------------------------------------------------------------------------
# Material property resolution
# ---------------------------------------------------------------------------


def resolve_material_properties(config: FitConfig, spec: LayerSpec) -> LayerSpec:
    """Resolve material= name to rho_cp/Sr/Sz values at config temperature."""
    if spec.material is None:
        return spec

    from fdtr.materials.loader import resolve_material

    mat = resolve_material(spec.material)
    T = config.temperature

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lib_rho_cp = float(mat.get_property_at_T(T, "rho_cp"))
        lib_Sz = float(mat.get_property_at_T(T, "Sz"))
        lib_Sr = float(mat.get_property_at_T(T, "Sr"))

    # Warn about sparse data or extrapolation
    if mat.n_points < 5:
        warnings.warn(
            f"Layer '{spec.material}': material has only {mat.n_points} data point(s). "
            f"Property values may be unreliable.",
            stacklevel=2,
        )
    if T < mat.T_min or T > mat.T_max:
        warnings.warn(
            f"Layer '{spec.material}': temperature {T} K is outside material "
            f"data range [{mat.T_min:.0f}, {mat.T_max:.0f}] K. Clamping applied.",
            stacklevel=2,
        )

    # Explicit conductivity schema wins over material-library symmetry.
    rho_cp = lib_rho_cp if "rho_cp" not in spec._explicit else spec.rho_cp
    is_user_isotropic = "S" in spec._explicit
    has_explicit_directional = bool(spec._explicit & {"Sr", "Sz"}) and not is_user_isotropic
    if is_user_isotropic:
        Sr = spec.Sr
        Sz = spec.Sz
        symmetry = SYMMETRY_ISOTROPIC
    elif has_explicit_directional:
        Sr = lib_Sr if "Sr" not in spec._explicit else spec.Sr
        Sz = lib_Sz if "Sz" not in spec._explicit else spec.Sz
        symmetry = SYMMETRY_TRANSVERSE
    else:
        Sr = lib_Sr
        Sz = lib_Sz
        symmetry = mat.symmetry

    if spec._explicit & {"S", "Sr", "Sz"}:
        if is_user_isotropic and mat.symmetry != SYMMETRY_ISOTROPIC:
            warnings.warn(
                f"Material '{spec.material}' is anisotropic but config uses S; "
                "using user's isotropic approximation.",
                stacklevel=2,
            )
        elif has_explicit_directional and mat.symmetry == SYMMETRY_ISOTROPIC:
            warnings.warn(
                f"Material '{spec.material}' is isotropic but config uses Sr/Sz; "
                "preserving anisotropic config behavior.",
                stacklevel=2,
            )

    return LayerSpec(
        name=spec.name,
        material=spec.material,
        rho_cp=rho_cp,
        Sr=Sr,
        Sz=Sz,
        d=spec.d,
        symmetry=symmetry,
        fit_fields=spec.fit_fields,
        _explicit=spec._explicit,
    )


# ---------------------------------------------------------------------------
# Guess resolution
# ---------------------------------------------------------------------------


def resolve_guess(config: FitConfig, target: TargetSpec) -> float:
    """Auto-resolve the initial guess for *target* from layer/fit values.

    Resolution rules:
        - ``spot_size`` -> ``config.spot_size``
        - ``TBC`` -> ``Sr`` of the first TBC layer (``rho_cp == 0``)
        - ``Sr_N`` -> resolved ``layers[N].Sr`` (material library aware)
        - ``Sz_N`` -> resolved ``layers[N].Sz`` (material library aware)
        - ``d_N`` -> ``layers[N].d``
        - ``rho_cp_N`` -> resolved ``layers[N].rho_cp`` (material library aware)
        - ``Sz_substrate`` -> ``Sz`` of the last non-TBC layer
        - ``Sr_substrate`` -> ``Sr`` of the last non-TBC layer

    If ``target.guess`` is explicitly set, it is returned unchanged.
    """
    if target.guess is not None:
        return target.guess

    name = target.name

    if name in {"Sr_substrate", "Sz_substrate"}:
        raise ValueError(
            f"Cannot auto-resolve guess for '{name}': use indexed Sr_N/Sz_N "
            "or S_N for isotropic layers."
        )

    if name == "spot_size":
        if config.spot_size is None:
            raise ValueError(
                "Cannot auto-resolve guess for 'spot_size': "
                "config.spot_size is not set."
            )
        return config.spot_size

    if name in ("spot_x", "spot_y"):
        if config.spot_size is None:
            raise ValueError(
                f"Cannot auto-resolve guess for '{name}': "
                "config.spot_size is not set."
            )
        return config.spot_size

    if name == "TBC":
        raise ValueError(
            "Cannot auto-resolve guess for bare 'TBC': "
            "use indexed name 'TBC_N' instead."
        )

    from fdtr.model.param import get_param_value

    try:
        stack = to_stack(config)
        return get_param_value(stack, name, spot_size_um=config.spot_size or 0.0)
    except ValueError as exc:
        raise ValueError(f"Cannot auto-resolve guess for '{name}': {exc}") from exc

    raise ValueError(
        f"Cannot auto-resolve guess for '{name}': "
        f"unrecognised target name."
    )


# ---------------------------------------------------------------------------
# Fit target resolution
# ---------------------------------------------------------------------------


def to_fit_targets(config: FitConfig) -> List:
    """Build resolved :class:`FitTarget` list.

    Targets are collected from three sources (merged in order):
    1. Layer ``fit_fields`` (``fit_Sr``, ``fit_TBC``, etc.)
    2. Spot fit fields (``fit_spot_size``, ``fit_spot_x``, ``fit_spot_y``)
    3. Legacy ``[[fit.targets]]`` entries (for backward compatibility)
    """
    from fdtr.common_types import FitTarget

    all_targets: list[TargetSpec] = []

    # 1. Layer fit_fields
    for i, layer in enumerate(config.layers):
        all_targets.extend(layer.to_targets(i))

    # 2. Spot fit fields
    if config.fit_spot_size is not None:
        all_targets.append(
            TargetSpec(
                name="spot_size",
                bounds=config.fit_spot_size,
                guess=config.spot_size,
            )
        )
    if config.fit_spot_x is not None:
        all_targets.append(
            TargetSpec(
                name="spot_x",
                bounds=config.fit_spot_x,
                guess=config.spot_size,
            )
        )
    if config.fit_spot_y is not None:
        all_targets.append(
            TargetSpec(
                name="spot_y",
                bounds=config.fit_spot_y,
                guess=config.spot_size,
            )
        )

    # 3. Legacy [[fit.targets]] -- add only names not already present
    existing_names = {t.name for t in all_targets}
    for t in config.targets:
        if t.name not in existing_names:
            all_targets.append(t)

    return [
        FitTarget(
            name=t.name,
            initial_guess=resolve_guess(config, t),
            bounds=t.bounds,
        )
        for t in all_targets
    ]


def collect_all_target_names(config: FitConfig) -> set[str]:
    """Collect target names from layer fit fields, spot fits, and legacy targets."""
    names: set[str] = set()
    for i, layer in enumerate(config.layers):
        names.update(target.name for target in layer.to_targets(i))
    if config.fit_spot_size is not None:
        names.add("spot_size")
    if config.fit_spot_x is not None:
        names.add("spot_x")
    if config.fit_spot_y is not None:
        names.add("spot_y")
    names.update(target.name for target in config.targets)
    return names
