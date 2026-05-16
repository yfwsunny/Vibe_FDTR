# FDTR Parameter Naming Conventions

## Parameter Table

| Name | Meaning | Unit |
|------|---------|------|
| `S_N` | Layer `N` isotropic thermal conductivity; writes `Sr_N` and `Sz_N` together | W/mK |
| `Sr_N` | Layer `N` in-plane thermal conductivity | W/mK |
| `Sz_N` | Layer `N` cross-plane thermal conductivity | W/mK |
| `d_N` | Layer `N` thickness | m |
| `rho_cp_N` | Layer `N` volumetric heat capacity | J/m^3K |
| `spot_size` | Beam 1/e^2 radius | um |
| `spot_x`, `spot_y` | Direction-specific beam 1/e^2 radius | um |
| `TBC_N` | Interface thermal conductance at layer `N` | W/m^2K |

`N` is 0-indexed from the top transducer layer.

## Layer Types

| Type | rho_cp | Sr/Sz | d | Notes |
|------|--------|-------|---|-------|
| Transducer | material value | material value | actual thickness (m) | Top layer, index 0 |
| TBC interface | **0.0** | conductance value | 1.0 | `rho_cp = 0` identifies a TBC layer |
| Semi-infinite substrate | material value | material value | **1.0** | Bottom layer |

## Fit Markers In TOML

In TOML config, fit targets use these fields on `[[layer]]` blocks:

- `fit_S = [lo, hi]` - fit isotropic conductivity with bounds; valid only on layers configured with `S = ...`
- `fit_Sr = [lo, hi]` - fit in-plane conductivity with bounds
- `fit_Sz = [lo, hi]` - fit cross-plane conductivity with bounds
- `fit_TBC = [lo, hi]` - fit interface conductance with bounds
- `fit_d = [lo, hi]` - fit layer thickness with bounds
- `fit_spot_x = [lo, hi]` - fit X-direction beam spot size
- `fit_spot_y = [lo, hi]` - fit Y-direction beam spot size

Top-level fit fields:

- `spot_size = <value>` - fixed beam 1/e^2 radius (um)
- `temperature = <K>` - measurement temperature

Schema rule: each material layer uses either `S` or `Sr`/`Sz`, never both.
Isotropic layers accept `S_N` only; anisotropic layers accept `Sr_N`/`Sz_N` only.
TBC layers accept `TBC_N` only.
