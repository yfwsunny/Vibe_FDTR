---
name: fdtr-uncertainty
description: Use when calculating FDTR parameter uncertainty, either standalone or from fitted results.
---

# FDTR Uncertainty

Uncertainty analysis estimates how known/input uncertainties propagate to target parameters. 

It can run standalone from a calculation config, or post-fit from a fit-result JSON.

For `iterfit`, uncertainty is evaluated step-by-step following the pipeline set in base config.

## Preconditions

- **Standalone mode**: MUST have a base config describing the calculation structure.  If no suitable base config exists, load `fdtr-config` first.  
- **Post-fit mode**: use a fit-result JSON when available. Do not reconstruct fitted state from report text or console output. Do not override the target parameters unless explicitly requested.

## Generate uncertainty config

Use `init-config --analysis uncertainty` from the base config.  

| Parameter                                  | Overrides base config? | Notes                                                                                                                                                                            |
| ------------------------------------------ | ----------------------:| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--base-config`                            | —                      | Required. Path to the base config.                                                                                                                                               |
| `--fit-result`                             | no                     | Path to fit-result JSON. Use for post-fit uncertainty.                                                                                                                           |
| `--strategy`                               | yes                    | `freqfit`, `offsetfit`, `spotfit`, or `iterfit`.                                                                                                                                 |
| `--signal`                                 | yes                    | `phase` by default. Usually keep default unless requested.                                                                                                                       |
| `--freq-range` / `--offset-range`          | yes                    | To modify, use repeatable `--freq-range "lo,hi"` and `--offset-range "lo,hi"`;                                                                                                   |
| `--phase-points` / `--offset-points`       | yes                    | Usually keep default unless requested.                                                                                                                                           |
| `--target-params` (repeat one per target.) | yes                    | Optional in standalone mode if base config has `fit_*` targets; optional in post-fit mode unless requested. Empty final targets are an error. Use `Param_INDEX` naming.          |
| `--known-param`(repeat one per target.)    | no                     | Known parameters uncertainty inputs, e.g. `d_0=0.03`. Repeat for multiple known uncertainties. Written to TOML as `known_params = {...}`. Default 0.05 for all known parameters. |
| `--full-output`                            | no                     | false by default. Use to return covariance matrix and per-parameter contribution breakdown.                                                                                      |

## Run uncertainty analysis

```bash
uv run fdtr uncertainty --config <task>/uncertainty.toml
```

## Caution

**DO NOT** override default uncertainties for known parameters unless explicitly requested.

**DO NOT** use `--full-output` unless explicitly requested.
