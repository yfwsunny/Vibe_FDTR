# FDTR Parameters & Layer Conventions

Core rules are inlined in `CLAUDE.md` Index Conventions section.
This file provides supplementary details: top-level fit fields and a full TOML example.

## Top-Level Fit Fields

- `temperature = <K>` - measurement temperature
- `[fit] spot_size = <value>` - fixed or initial beam 1/e² radius (um)
- `[fit] spot_x = <value>` - fixed X-direction beam radius (um)
- `[fit] spot_y = <value>` - fixed Y-direction beam radius (um)
- `[fit] fit_spot_size = [lo, hi]` - fit circular beam spot size
- `[fit] fit_spot_x = [lo, hi]` - fit X-direction beam spot size
- `[fit] fit_spot_y = [lo, hi]` - fit Y-direction beam spot size

## TOML Example

```toml
[[layer]]
material = "Gold"
d = 80e-9              # 80 nm transducer

[[layer]]               # TBC interface (auto-inserted)
rho_cp = 0.0            # identifies as TBC
Sr = 5.0e7              # TBC value in W/m^2K
Sz = 5.0e7
fit_TBC = [5.0e6, 5.0e8]

[[layer]]
material = "Graphite"
d = 1.0                 # semi-infinite substrate
fit_Sz = [0.6, 60.0]
```
