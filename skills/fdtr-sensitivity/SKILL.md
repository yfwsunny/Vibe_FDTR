---
name: fdtr-sensitivity
description: Use when evaluating FDTR parameter sensitivity.
---

# FDTR Sensitivity

Sensitivity is model-based: it perturbs the forward model and does not read
experimental data directly.

- Use `freqfit` and `offsetfit` as two independent analysis modes; run either or both as needed.
- Prefer broad `freq-range` / `offset-range` for sensitivity scans, then interpret useful sub-ranges from the results.
- For production `iterfit`, generate `freqfit` and/or `offsetfit` sensitivity configs from the same base stack.
- To compare design/model choices, generate and run one sensitivity config per variant. Use a short bash loop only for repeated, systematic variants.

## Preconditions

- **MUST** have a base config describing the calculation structure. If no suitable base config exists, load `fdtr-config` first to generate one.

## Generate sensitivity config

Use `init-config --analysis sensitivity` from the base config.

| Parameter                            | Overrides base config? | Notes                                                                                                               |
| ------------------------------------ | ----------------------:| ------------------------------------------------------------------------------------------------------------------- |
| `--base-config`                      | —                      | Required. Path to the base config.                                                                                  |
| `--strategy`                         | yes                    | **ONLY**  `freqfit` or  `offsetfit`. Usually need to override.                                                      |
| `--signal`                           | yes                    | `phase` by default. Usually keep default unless requested.                                                          |
| `--freq-range` / `--offset-range`    | yes                    | To modify, use repeatable `--freq-range "lo,hi"` and `--offset-range "lo,hi"`;                                      |
| `--phase-points` / `--offset-points` | yes                    | Usually keep default unless requested.                                                                              |
| `--parameters`                       | no                     | `all` by default. Parameters to calculate the sensitivity curves. Use `Param_INDEX` naming (see parameter-naming) . |
| `--delta`                            | no                     | Usually keep default unless requested.                                                                              |

## Run sensitivity analysis

```bash
uv run fdtr sensitivity --config <task>/sens_freq.toml
```

## Reading results

Focus on absolute sensitivity magnitude, not sign.

Assess which parameters dominate within the relevant frequency or offset range:

| Evidence                                   | Action                              |
| ------------------------------------------ | ----------------------------------- |
| large absolute sensitivity in target range | candidate fit target                |
| weak absolute sensitivity in target range  | fix or redesign measurement         |
| similar/correlated sensitivity curves      | avoid fitting together              |
| range-dependent sensitivity                | stage fit or restrict fitting range |

Return dominant parameters by range, correlated/weak parameters, recommended fit targets, fixed/constrained parameters, and measurement risks.
