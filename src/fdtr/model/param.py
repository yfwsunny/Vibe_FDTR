# src/fdtr/model/param.py
"""Unified parameter name resolution for multilayer stacks.

Consolidates parameter parsing, value retrieval, and mutation logic previously
spread across ``fit/param_resolver`` and ``analysis/sensitivity/sensitivity_params``.

This module depends ONLY on ``model/layer.py``.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from fdtr.model.layer import Layer, MultilayerStack, SYMMETRY_ISOTROPIC

# Properties that can be modified on a Layer.
_VALID_LAYER_PROPS = frozenset({"rho_cp", "Sr", "Sz", "d"})

# Short-form parameter names: S_N, Sr_N, Sz_N, d_N, rho_cp_N, TBC_N
_SHORT_PROP_RE = re.compile(r"^(S|Sr|Sz|d|rho_cp|TBC)_(\d+)$")


# ---------------------------------------------------------------------------
# ResolvedParam
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedParam:
    """Parsed description of a single optimisation / sensitivity parameter.

    Attributes:
        raw_name: Original parameter name string (e.g. ``"layer_0.Sr"``).
        kind: One of ``"layer_prop"``, ``"spot_size"``, ``"S"``, or ``"TBC"``.
        layer_index: Index into :attr:`MultilayerStack.layers`, or ``-1``
            when the parameter does not target a specific layer (e.g.
            ``spot_size``).
        property_name: Layer attribute being modified (``"Sr"``, ``"Sz"``,
            ``"d"``, ``"rho_cp"``), or ``""`` for non-layer params.
    """

    raw_name: str
    kind: str  # "layer_prop" | "spot_size" | "S" | "TBC"
    layer_index: int
    property_name: str


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------

def resolve(name: str, stack: MultilayerStack) -> ResolvedParam:
    """Parse a parameter name into a :class:`ResolvedParam`.

    Supported name formats:

    * **Special names**: ``spot_size``, ``spot_x``, ``spot_y``
    * **Short form**: ``S_N``, ``Sr_N``, ``Sz_N``, ``d_N``,
      ``rho_cp_N``, ``TBC_N``
    * **Dotted path**: ``layer_N.<prop>``

    Args:
        name: Parameter identifier.
        stack: Stack used to resolve aliases and validate indices.

    Returns:
        A fully resolved parameter descriptor.

    Raises:
        ValueError: If *name* cannot be parsed, references a layer out of
            range, or specifies an invalid property.
    """
    # --- special names ---------------------------------------------------
    if name in ("spot_size", "spot_x", "spot_y"):
        return ResolvedParam(
            raw_name=name, kind="spot_size", layer_index=-1, property_name=""
        )

    # --- short-form: S_N, Sr_N, Sz_N, d_N, rho_cp_N, TBC_N -------------
    m = _SHORT_PROP_RE.match(name)
    if m:
        prop = m.group(1)
        idx = int(m.group(2))
        if idx < 0 or idx >= stack.num_layers:
            raise ValueError(
                f"Layer index {idx} out of range for stack with "
                f"{stack.num_layers} layers."
            )
        if prop == "TBC":
            if not stack.layers[idx].is_tbc:
                raise ValueError(
                    f"Parameter '{name}' references layer {idx}, but that "
                    f"layer is not a TBC interface (rho_cp != 0)."
                )
            return ResolvedParam(
                raw_name=name, kind="TBC", layer_index=idx, property_name=""
            )
        if prop == "S":
            layer = stack.layers[idx]
            if layer.is_tbc:
                raise ValueError(
                    f"Parameter '{name}' references layer {idx}, but that "
                    f"layer is a TBC interface. Use 'TBC_{idx}' instead."
                )
            if layer.symmetry != SYMMETRY_ISOTROPIC:
                raise ValueError(
                    f"Parameter '{name}' references anisotropic layer {idx}. "
                    f"Use 'Sr_{idx}' or 'Sz_{idx}' instead."
                )
            return ResolvedParam(
                raw_name=name, kind="S", layer_index=idx, property_name=""
            )
        layer = stack.layers[idx]
        if layer.is_tbc:
            raise ValueError(
                f"Parameter '{name}' references TBC layer {idx}. "
                f"Use 'TBC_{idx}' instead."
            )
        if prop in {"Sr", "Sz"} and layer.symmetry == SYMMETRY_ISOTROPIC:
            raise ValueError(
                f"Parameter '{name}' references isotropic layer {idx}. "
                f"Use 'S_{idx}' instead."
            )
        return ResolvedParam(
            raw_name=name, kind="layer_prop", layer_index=idx, property_name=prop,
        )

    # --- dotted path: layer_N.<prop> -------------------------------------
    if "." in name:
        parts = name.split(".", 1)
        prefix, prop = parts[0], parts[1]

        if not prefix.startswith("layer_"):
            raise ValueError(
                f"Invalid parameter name '{name}': "
                f"expected 'layer_N.<prop>' format."
            )

        try:
            idx = int(prefix[len("layer_"):])
        except ValueError:
            raise ValueError(
                f"Invalid parameter name '{name}': "
                f"index after 'layer_' must be an integer."
            )

        if idx < 0 or idx >= len(stack.layers):
            raise ValueError(
                f"Layer index {idx} out of range for stack with "
                f"{len(stack.layers)} layers (0..{len(stack.layers) - 1})."
            )

        if prop not in _VALID_LAYER_PROPS:
            raise ValueError(
                f"Invalid property '{prop}' for layer parameter. "
                f"Must be one of {sorted(_VALID_LAYER_PROPS)}."
            )
        layer = stack.layers[idx]
        if layer.is_tbc:
            raise ValueError(
                f"Parameter '{name}' references TBC layer {idx}. "
                f"Use 'TBC_{idx}' instead."
            )
        if prop in {"Sr", "Sz"} and layer.symmetry == SYMMETRY_ISOTROPIC:
            raise ValueError(
                f"Parameter '{name}' references isotropic layer {idx}. "
                f"Use 'S_{idx}' instead."
            )

        return ResolvedParam(
            raw_name=name, kind="layer_prop", layer_index=idx, property_name=prop
        )

    # --- fallback --------------------------------------------------------
    raise ValueError(
        f"Unknown parameter name '{name}'. Expected 'layer_N.<prop>', "
        f"'S_N'/'Sr_N'/'Sz_N'/'d_N'/'rho_cp_N'/'TBC_N', 'spot_size', "
        f"'spot_x', or 'spot_y'."
    )


# ---------------------------------------------------------------------------
# get_param_value()
# ---------------------------------------------------------------------------

def get_param_value(
    stack: MultilayerStack,
    name: str,
    *,
    spot_size_um: float = 0.0,
) -> float:
    """Get the current value of a named parameter.

    Args:
        stack: The multilayer stack to read from.
        name: Parameter name (same formats accepted by :func:`resolve`).
        spot_size_um: Current spot size in micrometres (returned when
            *name* resolves to ``spot_size``).

    Returns:
        The parameter's current numerical value.
    """
    rp = resolve(name, stack)

    if rp.kind == "spot_size":
        return float(spot_size_um)

    layer = stack.layers[rp.layer_index]

    if rp.kind == "TBC":
        return float(layer.Sr)

    if rp.kind == "S":
        return float((layer.Sr + layer.Sz) / 2.0)

    return float(getattr(layer, rp.property_name))


# ---------------------------------------------------------------------------
# apply_params()
# ---------------------------------------------------------------------------

def apply_params(
    stack: MultilayerStack,
    spot_size_um: float,
    params: Dict[str, float],
    resolved: Dict[str, ResolvedParam],
) -> Tuple[MultilayerStack, Optional[float]]:
    """Apply fitted parameter values to a stack and return the new state.

    The original *stack* is never mutated; a new :class:`MultilayerStack` is
    returned.

    Args:
        stack: Original multilayer stack.
        spot_size_um: Current spot size in micrometres.
        params: Mapping of ``name -> fitted physical value``.
        resolved: Pre-validated mapping (e.g. from :func:`validate_targets`).

    Returns:
        ``(new_stack, new_spot_size_um)``.  *new_spot_size_um* is ``None``
        when no ``spot_size`` target is present.
    """
    new_spot: Optional[float] = None

    # Build a list of layers we can mutate
    layers: List[Layer] = [dataclasses.replace(l) for l in stack.layers]

    for name, value in params.items():
        rp = resolved[name]

        if rp.kind == "spot_size":
            new_spot = float(value)
            continue

        if rp.kind == "TBC":
            layers[rp.layer_index] = dataclasses.replace(
                layers[rp.layer_index], Sr=value, Sz=value
            )
            continue

        if rp.kind == "S":
            layers[rp.layer_index] = dataclasses.replace(
                layers[rp.layer_index], Sr=value, Sz=value
            )
            continue

        if rp.kind == "layer_prop":
            layers[rp.layer_index] = dataclasses.replace(
                layers[rp.layer_index], **{rp.property_name: value}
            )
            continue

    return MultilayerStack(layers), new_spot


# ---------------------------------------------------------------------------
# validate_targets()
# ---------------------------------------------------------------------------

def validate_targets(
    targets,
    stack: MultilayerStack,
    allow_spot: bool = True,
) -> Dict[str, ResolvedParam]:
    """Resolve and validate a collection of fit targets.

    Checks that every target name resolves, that no two targets write to the
    same ``(layer_index, property)`` pair, and that ``spot_size`` is only
    present when *allow_spot* is ``True``.

    Args:
        targets: Sequence of parameter name strings **or** :class:`FitTarget`
            objects (uses ``target.name``).
        stack: The multilayer stack.
        allow_spot: Whether a ``spot_size`` target is permitted.

    Returns:
        Mapping of ``name -> ResolvedParam``.

    Raises:
        ValueError: On resolution failure or conflicting targets.
    """
    resolved: Dict[str, ResolvedParam] = {}

    # Track (layer_index, property) pairs that have been claimed.
    # For TBC targets, both Sr and Sz of the TBC layer are claimed.
    claimed: set[Tuple[int, str]] = set()

    for target in targets:
        # Accept both bare strings and FitTarget objects
        name = target.name if hasattr(target, "name") else target
        rp = resolve(name, stack)

        # Spot-size gate
        if rp.kind == "spot_size" and not allow_spot:
            raise ValueError(
                f"Target '{name}' requests spot_size fitting, "
                f"but the current fitting strategy does not allow it."
            )

        # Conflict detection
        if rp.kind in {"S", "TBC"}:
            new_claims = {(rp.layer_index, "Sr"), (rp.layer_index, "Sz")}
        elif rp.kind == "layer_prop":
            new_claims = {(rp.layer_index, rp.property_name)}
        else:
            # spot_size -- no layer claims
            new_claims = set()

        conflicts = new_claims & claimed
        if conflicts:
            # Find the name of the earlier target that conflicts
            conflict_names = [
                rn for rn, prev in resolved.items()
                if _claims_of(prev) & conflicts
            ]
            raise ValueError(
                f"Target '{name}' conflicts with "
                f"{', '.join(conflict_names)}: both write to "
                f"{conflicts}."
            )

        claimed |= new_claims
        resolved[name] = rp

    return resolved


# ---------------------------------------------------------------------------
# default_parameter_names()
# ---------------------------------------------------------------------------

def default_parameter_names(stack: MultilayerStack) -> List[str]:
    """Generate all valid parameter names for *stack*.

    Produces ``spot_size`` first, then per-layer names.  For TBC layers only
    ``TBC_N`` is emitted.  For regular layers ``Sr_N``, ``Sz_N``,
    ``rho_cp_N`` are always emitted, and ``d_N`` is omitted for the
    semi-infinite substrate (``d == 1.0``).

    Args:
        stack: The multilayer stack.

    Returns:
        Ordered list of parameter name strings.
    """
    names: List[str] = ["spot_size"]

    for idx, layer in enumerate(stack.layers):
        if layer.is_tbc:
            names.append(f"TBC_{idx}")
            continue

        if layer.symmetry == SYMMETRY_ISOTROPIC:
            names.append(f"S_{idx}")
        else:
            names.append(f"Sr_{idx}")
            names.append(f"Sz_{idx}")
        if not _is_semi_infinite_substrate(stack, idx):
            names.append(f"d_{idx}")
        names.append(f"rho_cp_{idx}")

    return names


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_semi_infinite_substrate(stack: MultilayerStack, idx: int) -> bool:
    """Return True if layer *idx* is the semi-infinite substrate."""
    return idx == stack.substrate_index and stack.layers[idx].d == 1.0


def _claims_of(rp: ResolvedParam) -> set[Tuple[int, str]]:
    """Return the set of ``(layer_index, property)`` pairs claimed by *rp*."""
    if rp.kind == "TBC":
        return {(rp.layer_index, "Sr"), (rp.layer_index, "Sz")}
    if rp.kind == "S":
        return {(rp.layer_index, "Sr"), (rp.layer_index, "Sz")}
    if rp.kind == "layer_prop":
        return {(rp.layer_index, rp.property_name)}
    return set()
