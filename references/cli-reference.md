# FDTR CLI Reference

All commands run via `uv run fdtr <subcommand>`.

## Fitting Commands

| Command | Purpose | Key flags |
|---|---|---|
| `fdtr fit --config <toml>` | Unified entry that reads strategy from config | (none required) |

All fit commands always produce PNG + CSV + JSON output artifacts. No flags are needed to enable output.

### Agent Workflow

Agent-driven fits should use config-only invocation with auto-naming:

```bash
uv run fdtr fit --config <config.toml>
```

**Do not** pass `--output` or `--output-dir` unless the user explicitly requests a specific output path.

### Manual Usage

Human users or tutorials may pass `--output-dir` to override the runtime output location:

```bash
uv run fdtr fit --config <config.toml> --output-dir ./my_results
```

## Analysis Commands

| Command | Purpose | Key flags |
|---|---|---|
| `fdtr sensitivity --config <toml>` | Parameter sensitivity analysis | output: CSV + PNG |
| `fdtr uncertainty --config <toml>` | Standalone uncertainty analysis | `--fit-result <json>` |
| `fdtr uncertainty --fit-result <json>` | Post-fit uncertainty analysis | optional `--config <toml>` |

## Summary Command

| Command | Purpose | Key flags |
|---|---|---|
| `fdtr summary <task_dir>` | Generate cross-analysis Markdown report | `--output`, `--organize` |

`fdtr summary` scans a task directory for fit results, sensitivity CSVs, uncertainty JSONs, plots, and configs, then produces a unified Markdown report.

- `--output <path>`: Explicit output path for the summary Markdown file
- `--organize`: Move configs/scan-data into `inputs/` and plots/CSVs/JSONs into `results/` before generating report

## Config And Utility Commands

| Command | Purpose |
|---|---|
| `fdtr scan-data <dir>` | Index a data directory and emit grouped JSON |
| `fdtr init-config --strategy <name>` | Generate a fit TOML template |
| `fdtr init-pipeline [--config <toml>]` | Generate a pipeline TOML template; with config, targets are symmetry-aware |
| `fdtr list-materials` | List materials in the library, including symmetry |
| `fdtr show-material <name> -T <K>` | Show material properties and symmetry at temperature |

## scan-data Workflow

Use `scan-data` in two steps:

```bash
# Step 1: index groups
uv run fdtr scan-data ./Data

# Step 2: fetch one group in detail when needed
uv run fdtr scan-data ./Data --group sample_a --save
```

Notes:
- the first call gives stable `group_key` values
- if many groups are found, the first call may return only indexes
- the second call saves a detailed path spec for one group, usually named
  `scan_group_<group_key>.json` under the active task/session directory

## init-config Path Input

Canonical path input for `init-config`:

```bash
uv run fdtr init-config \
  --strategy iterfit \
  --transducer Gold \
  --substrate Graphite \
  --paths-spec paths.json \
  --output iterfit.toml
```

Alternative inline form:

```bash
uv run fdtr init-config \
  --strategy iterfit \
  --transducer Gold \
  --substrate Graphite \
  --paths-json '{"group_key":"sample_a","offset_x":{"pattern":"*sample_a*xscan*"},"freq_sweep":{"pattern":"*sample_a*image*"}}' \
  --output iterfit.toml
```

Use `--paths-json` only for small manual or agent-generated edits. Prefer `--paths-spec` for normal workflow.

## init-config Analysis Templates

Sensitivity and uncertainty use flat analysis TOML files that point to a base fit config via `base_config`.

```bash
# Step 1: generate a base fit config
uv run fdtr init-config \
  --strategy iterfit \
  --transducer Gold \
  --substrate Graphite \
  --paths-spec paths.json \
  --output iterfit.toml

# Step 2: generate analysis configs from the base config
uv run fdtr init-config --analysis sensitivity --base-config iterfit.toml --output sens.toml
uv run fdtr init-config --analysis uncertainty --base-config iterfit.toml --output unc.toml
```

For uncertainty templates, use:

- `known_params = { ... }`
- `full_output = true|false`

The uncertainty calculation path is inferred internally from `strategy`:

- `freqfit -> freq`
- `offsetfit -> offset`
- `spotfit -> fwhm`
- `iterfit -> pipeline step fitter`

Do not use `known_param`, `mode`, `offset_sweep`, `both`, or `contributions`.

## init-config Strategies

| Strategy | Purpose |
|---|---|
| `freqfit` | Freq-sweep fit config |
| `offsetfit` | Offset-scan fit config |
| `spotfit` | FWHM spot-size fit config |
| `iterfit` | Pipeline fit config |

## init-config Core Options

| Flag | Purpose |
|---|---|
| `--strategy <name>` | Choose `freqfit`, `offsetfit`, `spotfit`, or `iterfit` |
| `--transducer <material>` | Top-layer material |
| `--substrate <material>` | Bottom-layer material |
| `--layer <material>` | Add an intermediate layer, repeatable |
| `--temperature <K>` | Temperature in Kelvin |
| `--paths-spec <file>` | Canonical file-based path spec |
| `--paths-json <json>` | Inline path spec |
| `--fit "Param_N=lo,hi"` | Fit bounds, repeatable |
| `--output <path>` | Output TOML path |
| `--report` | ~~Removed — use `fdtr summary` instead~~ |
| `--full-template` | Emit the verbose reference-style template instead of the lean task template |

Default `init-config` output is lean and task-oriented. It omits unset path
stubs, default `average = true`, and commented range examples. Use `examples/config-full-template.toml` when a reader needs a single commented reference covering all currently supported TOML fields.

Use `S = ...` in isotropic layer configs and `--fit "S_N=lo,hi"` when one
fitted conductivity should remain coupled. Use `Sr`/`Sz` plus
`Sr_N`/`Sz_N` only for anisotropic layers.

## init-config Range Flags

Use only the repeatable singular forms in documentation:

```bash
--freq-range "1e4,1e6" --freq-range "5e6,2e7"       # Hz
--offset-range "0,20" --offset-range "30,60"         # µm (NOT meters)
```

Do not document `--freq-ranges` or `--offset-ranges` in user guidance.

The TOML schema still accepts `freq_ranges` and `offset_ranges` for multiple
intervals. Agents should create them through repeatable `--freq-range` and
`--offset-range` flags rather than hand-writing plural CLI options.

## Example TOML Files

- `examples/freqfit.toml`, `examples/offsetfit.toml`, `examples/spotfit.toml`,
  and `examples/iterfit.toml` are lean generated strategy examples.
- `examples/sensitivity.toml` and `examples/uncertainty.toml` are flat analysis
  config examples that point to a base fit config.
- `examples/config-full-template.toml` is the human reference template with
  English comments and all currently supported config fields.
- `tests/benchmarks/expected_*_4layer.toml` fixtures intentionally track lean
  generated output only.

## Common Fit Flags

| Flag | Used with | Purpose |
|---|---|---|
| `--config <toml>` | all fit and analysis commands | path to TOML config |
| `--signal phase|amplitude` | `freqfit`, `offsetfit` | choose signal channel |
| `--output-dir <path>` | manual usage only | override runtime output location |

**Removed flags** (output is now always-on):
- `--report`: replaced by `fdtr summary <task_dir>`
- `--no-plot`: plots are always saved to disk (Agg backend)

Removed legacy strategy subcommands and direct-mode args (`--strategy`, positional data args):
- `fdtr freqfit`, `fdtr offsetfit`, `fdtr spotfit`, `fdtr iterfit`
- `fdtr fit --strategy <name> ...` (direct-arg invocation)

Use `fdtr fit --config <toml>` instead.
