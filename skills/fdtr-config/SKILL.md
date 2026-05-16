---
name: fdtr-config
description: Use when generating or editing FDTR TOML configs.
---

# FDTR Config

Generate configs with `init-config`; **Do not** hand-write full TOML files. Use
targeted edits only for values the CLI cannot infer safely.

## Before init-config

Every important value must be either user-provided, scanner-derived, inherited from an existing config, inferred with a stated reason, or explicitly defaulted.

The following args are usually needed to append:

Index rule: use `Param_INDEX` names such as `Sr_2`, `Sz_2`, `d_0`, and `TBC_1`; do not use semantic aliases.

| Resolve                                                          | Value/source                                                                                                                      | Must ask if                                           |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Data state / paths (`--paths-spec`)                              | path spec from `fdtr scan-data`, or no-data (omit `--paths-spec`)                                                                 |                                                       |
| Strategy (`--strategy`)                                          | `freqfit`, `offsetfit`, `spotfit`, or `iterfit`                                                                                   | cannot infer from request                             |
| Stack (`--transducer`, `--layer`, `--substrate`)                 | material names plus finite thicknesses **in meters**: `Transducer:thickness`, repeated `Layer:thickness`, and substrate name only | any layer identity is missing                         |
| Temperature (`--temperature`)                                    | user value or default `295.15 K`                                                                                                  | non-room-temperature likely                           |
| Fit targets (repeat one `--fit "Param_INDEX=lo,hi"` per target.) | Target params and bounds from request or pipeline (iterfit only).                                                                 | target is ambiguous                                   |
| Offset fit frequencies (`--freq-offset`)                         | with path spec reads `offset_freqs_hz` and display to user, defaults to the lowest remaining offset-scan frequency.               | Whenever offsetfit is used (except pure spot fitting) |

**Do not pass these flags during `init-config` unless requested to change:**

| Default group                                  | Default behavior                                                                                                       |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Spot size (`--spot-size`)                      | `3.0 um`                                                                                                               |
| Signal (`--signal`)                            | `phase`, can be changed to `amplitude` upon request                                                                    |
| Spot fit frequencies (  `--freq-spot`)          | no-data (`5.0e7 Hz`) or with path spec (the highest offset-scan frequency from `offset_freqs_hz`)                      |
| Sampling (`--offset-points`, `--phase-points`, | `100`, `80`                                                                                                            |
| Data ranges (`--freq-range`, `--offset-range`) | Full data range. To modify, use repeatable `--freq-range "lo,hi"`(in Hz) and `--offset-range "lo,hi"`(in micrometers); |
| Pipeline (`--pipeline`, `--iterations`)        | default pipeline (fit x spot, y spot-Sr_2-Sz_2,TBC_1), `6` iterations                                                  |
| Output (`--output`)                            | keep auto output path unless requested                                                                                 |

## Targeted edits

After generation, edit only material property overrides, fixed TBC values. Do not replace the whole file or restructure generated sections.
For `spotfit`, review `freq_spot` against the selected scan frequency before running the fit; keep `freq_offset` aligned with the offset-fit dataset.

## Material ambiguity

Exact library names pass through. User-provided values override after generation
without lookup. For fuzzy names, run `uv run fdtr list-materials` once, shortlist
at most three candidates, and run `uv run fdtr show-material <name> -T <K>` only
for those. Resolve once and reuse.

## Caution

**Must** ask user to inspect and confirm the generated config file before proceeding to fit or analysis.

All config paths (pipeline, offset_dir, phase_dir, etc.) : absolute paths are used as-is, while relative paths are resolved relative to the config file's parent directory.
