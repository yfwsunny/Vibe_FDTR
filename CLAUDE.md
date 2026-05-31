# FDTR Toolkit

Classify the FDTR task, then load only the next needed skill.

## Routing

1. **Data or no data**
- If the user has FDTR data to process, first run `uv run fdtr scan-data <data_dir>`. **Do not** inspect raw directories or measurement files before scanner discovery.

- Use the first scan output to discover stable `group_key` values and the dataset organization.

- If a group is selected, save its paths spec with:
  `uv run fdtr scan-data <data_dir> --group <group_key> --save`

- If all discovered groups should be processed, save all group path specs with:
  `uv run fdtr scan-data <data_dir> --save-all`

- If no data is involved, do not run `scan-data`.
2. **Config**
- If no existing config is mentioned, load `.claude/skills/fdtr-config/SKILL.md`.

- `fdtr-config` defines the study structure, layer stack, materials, targets, fixed/fitted parameters, bounds, and full parameter list.

- **Do not** hand-write full TOML files.

- Built-in material files live in `src/fdtr/materials/data/`; use `uv run fdtr list-materials` and `uv run fdtr show-material <name> -T <K>` before searching files. In configs, use the material stem such as `Gold_new`, not `Gold_new.txt`.
3. **Core function**

Load only what the user asks for:

- fitting

- sensitivity -> `.claude/skills/fdtr-sensitivity/SKILL.md`

- uncertainty -> `.claude/skills/fdtr-uncertainty/SKILL.md`
4. **Summary**

Generate a unified report only when requested by `uv run fdtr summary <task_dir>`. **Do not** use `uv run fdtr summary <task_dir> --organize` unless explicitly requested to reorganize files and generate a report.

## Index Conventions

Layer indexing is 0-based from top to bottom:

| Index    | Layer Type     | Key Properties                                           |
| -------- | -------------- | -------------------------------------------------------- |
| 0        | Transducer     | All material props; `d` = actual thickness (m)           |
| Odd      | TBC interface  | `rho_cp = 0`; `Sr`/`Sz` = conductance (W/m²K); `d = 1.0` |
| Even > 0 | Material layer | All material props; substrate: `d = 1.0` (semi-infinite) |

Parameter names (`N` = layer index):

| Name                              | Meaning                                      | Unit  |
| --------------------------------- | -------------------------------------------- | ----- |
| `S_N`                             | Isotropic conductivity (sets both Sr and Sz) | W/mK  |
| `Sr_N` / `Sz_N`                   | In-plane / cross-plane conductivity          | W/mK  |
| `d_N`                             | Layer thickness                              | m     |
| `rho_cp_N`                        | Volumetric heat capacity                     | J/m³K |
| `TBC_N`                           | Interface conductance at TBC layer N         | W/m²K |
| `spot_size` / `spot_x` / `spot_y` | Beam 1/e² radius                             | µm    |

Rules:

- `TBC_N` is one interface conductance; do not split into `Sr_N`/`Sz_N` targets.
- Use `S_N` for isotropic layers, `Sr_N`/`Sz_N` for anisotropic layers.
- TOML fit markers: `fit_S`, `fit_Sr`, `fit_Sz`, `fit_TBC`, `fit_d`, `fit_rho_cp` = `[lo, hi]`.
- `init-config` auto-inserts TBC layers between material layers.

Spot usage by workflow:

| Workflow                                                               | Spot rule                                                              |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `freqfit`, standalone `offsetfit`, sensitivity, standalone uncertainty | Use `spot_size`                                                        |
| Directional `spotfit`                                                  | May use `spot_x` / `spot_y`; report average as `spot_size`             |
| `iterfit`                                                              | Pipeline `spot_key` selects `spot_x`, `spot_y`, or average `spot_size` |

Do not use `spot_x` / `spot_y` in normal configs unless the workflow explicitly needs directional offset spots.

## Fit Execution

Run only config-driven fits: `uv run fdtr fit --config <config.toml>`.

Before fitting, make sure:

- config exists
- all fit commands always produce PNG + CSV + JSON artifacts. No flags are needed to enable output.

Fit strategy:

- `freqfit`: for standard frequency-sweep data at fixed pump-probe offset, usually 0.
- `offsetfit`: for pump-probe beam offset scans at fixed frequency. Usually considered for in-plane/lateral thermal properties.
- `spotfit`: fit spot size from offset scans at a high frequency.
- `iterfit`: pipeline framework that chains multiple fitting steps (e.g. offset then freq) in a single iteration loop. **Use iterfit with a custom pipeline** when the user describes a multi-step fitting procedure (e.g. "first fit A from offset, then fit B from freq, repeat"). **Do not** orchestrate separate freqfit/offsetfit runs for such workflows.

Do not use `iterfit` as a sensitivity strategy.

To customize the pipeline, load `.claude/skills/fdtr-iterpipeline/SKILL.md`.

## Execution Rules

Do not pass output-path override flags in agent workflows. Init commands and scan-data saves use auto-generated task paths.

By default, after completing a requested FDTR command, do not provide a detailed summary unless the user asks.

Built-in pipelines use `builtin:<name>` such as `builtin:default`. File paths for pipeline, offset_dir, phase_dir, and other config paths use absolute paths as-is; relative paths are resolved relative to the config file's parent directory.

## Out-of-workflow Tasks

When a user request is slightly outside the routed skill flow, first try to express it through existing scan-data, paths-spec, init-config, config fields, pipeline, and config-driven fit behavior. Any temporary analysis or helper work must return to those standard FDTR inputs or task artifacts; do not replace scan-data, init-config, built-in averaging, pipeline execution, or `uv run fdtr fit --config <config.toml>` with an ad hoc implementation.

Consult the following references and related examples. Do not read `src/` unless explicitly requested.

| File                             | Content                                                                  |
| -------------------------------- | ------------------------------------------------------------------------ |
| `references/skill_capability.md` | Capability boundaries, standard inputs/outputs, and source-reading gates |
| `references/cli-reference.md`    | Complete CLI command and flag reference                                  |
| `references/data-formats.md`     | Data file formats: offset-scan and freq-sweep                            |
