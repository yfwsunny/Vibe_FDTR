# FDTR Layer Conventions

## Layer Indexing

Layers are **0-indexed from top** (transducer) to bottom (substrate).

Example 3-layer stack: Au (index 0) / TBC (index 1) / Graphite (index 2).

## Layer Types

### Transducer Layer (index 0)

- Top-most layer (the metallic transducer)
- All properties from material database or manual entry
- `d` = actual physical thickness in meters (e.g. `80e-9` for 80 nm)
- Isotropic transducers use `S = ...` and may fit `fit_S`
- Anisotropic transducers use `Sr`/`Sz` and may fit `fit_Sr`, `fit_Sz`, `fit_d`

### TBC Interface Layer

- Inserted between each pair of material layers
- Identified by `rho_cp = 0`
- `Sr` and `Sz` hold the thermal boundary conductance value (W/m^2K)
- `d = 1.0` (placeholder, not used)
- Can fit `fit_TBC = [lo, hi]`

### Semi-infinite Substrate (bottom layer)

- Bottom-most layer
- All properties from material database or manual entry
- `d = 1.0` - this flag marks it as semi-infinite (not a real thickness)
- Isotropic substrates use `S = ...` and may fit `fit_S`
- Anisotropic substrates use `Sr`/`Sz` and may fit `fit_Sr`, `fit_Sz`

### Isotropic Conductivity Fit

Use `S = value` plus `fit_S = [lo, hi]` on an isotropic material layer. The generated target is `S_N`, and fitting, sensitivity, and uncertainty perturb one coupled conductivity.

## Auto-Insertion In init-config

When using `fdtr init-config`, TBC interface layers are auto-inserted between material layers. A 2-material stack (Au + Graphite) becomes 3 layers: Au / TBC / Graphite.

## TOML Example

```toml
[[layer]]
material = "Gold"
d = 80e-9              # 80 nm transducer

[[layer]]               # TBC interface (auto-inserted)
rho_cp = 0.0            # identifies as TBC
Sr = 5.0e7              # TBC value in W/m^2K
Sz = 5.0e7

[[layer]]
material = "Graphite"
d = 1.0                 # semi-infinite substrate
```
