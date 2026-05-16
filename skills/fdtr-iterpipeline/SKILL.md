---
name: fdtr-iterpipeline
description: Use when the user wants to create or customize an iterative fitting pipeline TOML for fdtr-iterfit. Triggers on "pipeline", "iterfit steps", "customize pipeline", "迭代流程", "pipeline toml".
---

# FDTR iterfit pipeline generation

## What This Does

Creates or customizes iterative fitting pipeline TOML files that define the step sequence for fdtr-iterfit. Each pipeline specifies an ordered list of fitting steps executed iteratively until convergence.

## Prerequisites

- Understanding of which parameters to fit and in what order
- fdtr-iterfit config file (use fdtr-config with `--strategy iterfit`)

## Execution

### Generate default pipeline

```bash
uv run fdtr init-pipeline --output pipeline.toml
```

### Pipeline Structure

Each `[[step]]` block has these fields:

| Field            | Required | Description       | Values                                                        |
| ---------------- | -------- | ----------------- | ------------------------------------------------------------- |
| `name`           | yes      | Step identifier   | any string                                                    |
| `fitter`         | yes      | Fitting engine    | `fwhm`, `offset`, `freq`                                      |
| `signal`         | no       | Signal type       | `phase`, `amplitude`; required for `freq` and `offset`        |
| `data_key`       | yes      | Dataset to use    | `offset_dir`, `offset_dir_y`, `offset_dir_phase`, `phase_dir` |
| `target_names`   | yes      | Parameters to fit | e.g. `["spot_x"]`, `["Sr_2"]`                                 |
| `spot_key`       | no       | Spot size to use  | `spot_x`, `spot_y`, `spot_size` (default: `spot_size`)        |
| `freq_ranges`    | no       | Freq intervals    | list of `[lo, hi]` in Hz; overrides config `freq_ranges`      |
| `offset_ranges`  | no       | Offset intervals  | list of `[lo, hi]` in um; overrides config `offset_ranges`    |
| `freq_offset`    | no       | Offset frequency  | Hz; overrides config `freq_offset` (offset steps only)        |

Top-level fields: `name` (pipeline name) and `convergence_tol` (default 1e-4).

**Iteration count** is set in the config TOML (`[fit]` section `iterations`), not in the pipeline.

### Step-Level Parameter Override

`freq_ranges`, `offset_ranges`, and `freq_offset` can be set per step to override config-level values. When absent, the config value is used. Priority: **step > config > full-data range**.

Rules:
- `fwhm` steps implicitly ignore `offset_ranges` (FWHM uses full offset data).
- `freq_offset` only affects `offset` steps.
- `freq_ranges` only affects `freq` steps.

### Default Pipeline (4 steps)

1. **spot_x**: FWHM fitter on X-offset data → fits `spot_x`
2. **spot_y**: FWHM fitter on Y-offset data → fits `spot_y`
3. **sr**: Offset fitter on X-offset phase using `spot_x` → fits `Sr_2`
4. **sz_tbc**: Freq fitter on phase using `spot_size` → fits `Sz_2`, `TBC_1`

See `examples/pipeline.toml` for a complete example with comments.

### Customization

- **Reorder**: change step order in the TOML. Earlier results feed into later steps.
- **Remove**: delete unwanted `[[step]]` blocks. Minimum: one step.
- **Add**: new `[[step]]` blocks with `name`, `fitter`, and `target_names`.
- **Change targets**: modify `target_names` list per step.
- **Narrow ranges**: set `freq_ranges` or `offset_ranges` on a step to constrain fitting.
- **Override freq_offset**: set `freq_offset` on an offset step to use a different frequency.

### Example: Step-Level Override

```toml
[[step]]
name = "sr"
fitter = "offset"
signal = "phase"
data_key = "offset_dir_phase"
target_names = ["Sr_2"]
spot_key = "spot_x"
freq_offset = 2.0e6           # use 2 MHz instead of config freq_offset
offset_ranges = [[-10, 10]]   # narrow offset range for this step
```

## Output

- Pipeline TOML file at specified path

## Next Steps

- **fdtr-iterfit** — run the pipeline
