---
name: fdtr-iterpipeline
description: Use when the user wants to create or customize an iterative fitting pipeline TOML for fdtr-iterfit. Also when the user describes a multi-step fitting procedure (alternating offset/freq fits, "first fit X then fit Y and repeat", iterative parameter coupling). Triggers on "pipeline", "iterfit steps", "customize pipeline", "iterative fitting procedure", "alternating fit", "迭代流程", "pipeline toml".
---

# FDTR iterfit pipeline generation

#### Built-in Pipeline Check

Before creating a custom pipeline, check whether an existing built-in pipeline can express the requested step order and targets. Prefer a built-in reference when it matches the study; write a custom pipeline only when the built-in pipeline does not match the required data keys, target parameters, spot handling, step order, or step-level ranges.

Currently documented built-in:

| Reference         | Step sequence                                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `builtin:default` | `spot_x` from X offset amplitude -> `spot_y` from Y offset amplitude -> `Sr_2` from X offset phase using `spot_x` -> `Sz_2` + `TBC_1` from frequency phase using average `spot_size` |

Built-in pipelines could be directly used in config file. e.g. `pipeline = "builtin:default"`.

## File Location

Custom pipeline TOML files are task assets. Keep them with the task config unless
there is a clear reason not to. The config may reference them by absolute path or
by relative path resolved from the config file's directory:

```toml
[fit]
pipeline = "pipeline_<descriptive>.toml"
```

Prefer generated absolute POSIX-style paths in configs on Windows.

## Prerequisites for writing a new pipeline

Before writing a pipeline, you MUST have:

1. A completed iterfit config (generated via `init-config --strategy iterfit`)
2. Understanding of the layer stack, material symmetry, and parameter physical meaning for the study
3. Understanding of the iteration strategy: which parameter to fit from which data in what order

If the config has not been generated or you cannot explain each parameter's physical role, stop and complete config generation first.

## Template Reference

Read `examples/pipeline.toml` for a complete annotated example covering all fields. Use it as the starting point for every new pipeline. Do NOT directly edit the example file.

## Field Reference

### Top-level fields

| Field             | Required | Default | Description                              |
| ----------------- | -------- | ------- | ---------------------------------------- |
| `name`            | yes      | —       | Pipeline identifier                      |
| `convergence_tol` | no       | 1e-4    | Relative-change threshold for early stop |

**Iteration count** is set in the config TOML (`[fit]` section `iterations`), not in the pipeline.

### Step fields

Each `[[step]]` block:

| Field           | Required                   | Description                                         |
| --------------- | -------------------------- | --------------------------------------------------- |
| `name`          | yes                        | Human-readable step label                           |
| `fitter`        | yes                        | `"fwhm"` \| `"freq"` \| `"offset"`                  |
| `signal`        | freq/offset: yes; fwhm: no | `"phase"` \| `"amplitude"`                          |
| `data_key`      | yes                        | Key in loaded datasets (see data_key table below)   |
| `target_names`  | yes                        | Parameters to fit, e.g. `["spot_x"]`, `["Sr_2"]`    |
| `spot_key`      | no                         | `"spot_x"` \| `"spot_y"` \| `"spot_size"` (default) |
| `freq_ranges`   | no                         | List of `[lo, hi]` in Hz; overrides config          |
| `offset_ranges` | no                         | List of `[lo, hi]` in um; overrides config          |
| `freq_offset`   | no                         | Hz; overrides config (offset steps only)            |

### data_key values

| data_key             | Produced by             | Typical fitter |
| -------------------- | ----------------------- | -------------- |
| `offset_x_amplitude` | X-direction offset scan | `fwhm`         |
| `offset_y_amplitude` | Y-direction offset scan | `fwhm`         |
| `offset_x_phase`     | X-direction offset scan | `offset`       |
| `offset_y_phase`     | Y-direction offset scan | `offset`       |
| `freq_phase`         | Frequency sweep         | `freq`         |

`data_key` must match a key in the loaded datasets at runtime. A typo causes a hard validation error (step will NOT be silently skipped).

### target_names notes

- Use `Param_INDEX` naming: `Sr_2`, `Sz_2`, `d_0`, `TBC_1`
- For isotropic layers, use `S_N` (not `Sr_N`/`Sz_N`)
- Beam parameters: `spot_size`, `spot_x`, `spot_y`
- Every target must have fit bounds defined in the config

### Step-level Override Priority

step > config > full-data range

Rules:

- `fwhm` steps implicitly ignore `offset_ranges` (FWHM uses full offset data)
- `freq_offset` only affects `offset` steps
- `freq_ranges` only affects `freq` steps

## Validation

Pipeline TOML is validated at iterfit startup. Minimum 2 steps required. All errors are reported at once — there is no silent skipping of steps.

## Prohibitions

- Do NOT directly edit `examples/pipeline.toml` or built-in templates
- Do NOT write a pipeline before completing config generation
- Do NOT use bare `pipeline = "default"`; use `pipeline = "builtin:default"`

## Next Steps

After selecting or writing the pipeline, update the config's `pipeline` field if needed, then run: `uv run fdtr fit --config <config.toml>`
