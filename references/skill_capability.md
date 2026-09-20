# FDTR Skill Capability

This reference describes what the project-level skills and CLI are expected to
cover. Use it when a request does not fit cleanly into one existing skill, or
when deciding whether a task should be handled through existing FDTR inputs
rather than source-code inspection or ad hoc execution.

Do not use this document as a replacement for the routed skills. Use
`CLAUDE.md` first, then the task-specific skill, and read this document only
when the task crosses a skill boundary or the existing capability is unclear.

## Operating Contract

FDTR agent workflows are config-driven:

- Data discovery starts with `scan-data`.
- Study setup starts from `init-config` or an existing reviewed config.
- Fitting and analysis run from config files.
- Generated artifacts are kept under task directories.
- Temporary helper work should return to standard FDTR inputs or artifacts.

The agent may reason, inspect generated artifacts, and prepare task-local helper
outputs, but should not replace the standard workflow entry points with a
parallel implementation.

## Capability Map

| Area | Primary interface | Standard output | Notes |
| --- | --- | --- | --- |
| Data discovery | `scan-data` | group summaries, saved paths specs | Use before inspecting measurement files. |
| Data selection | paths spec or config `[paths]` fields | selected directories, patterns, or explicit file lists | Keep selections expressible by generated configs when possible. |
| Multi-file averaging | `[fit] average = true` | averaged arrays inside loaders, fit artifacts | Averaging is built into the data-loading path. |
| Config generation | `init-config` plus `fdtr-config` | task TOML config | Do not hand-write full configs. |
| Layer and parameter mapping | `CLAUDE.md`, `parameter-and-layers.md`, `fdtr-config` | layer stack and fit markers | Use indexed names such as `S_2`, `Sz_2`, `TBC_1`. |
| Single-mode fitting | `fit --config` with `freqfit`, `offsetfit`, or `spotfit` | PNG, CSV, JSON | Do not use direct-mode fit arguments. |
| Multi-step fitting | `iterfit` config plus pipeline | pipeline fit artifacts | Use `fdtr-iterpipeline` for custom pipelines. |
| Sensitivity | `fdtr-sensitivity`, `sensitivity --config` | sensitivity CSV and PNG | Do not use `iterfit` as a sensitivity strategy. |
| Uncertainty | `fdtr-uncertainty`, `uncertainty --config` or fit result | uncertainty JSON and related outputs | Prefer post-fit uncertainty from fit result JSON when applicable. |
| Summary | `summary <task_dir>` | Markdown report | Use only when requested. |

## Standard Inputs And Outputs

Agents should prefer these handoff formats:

- Saved scan-data path specs for dataset organization and group identity.
- Generated TOML configs for stack, parameters, paths, fit ranges, and strategy.
- Pipeline TOML files for iterfit step order and step-level overrides.
- Fit, sensitivity, uncertainty, and summary artifacts under task directories.

If a helper step is needed, its result should be one of these standard inputs or
a task artifact that helps interpret them.

## Boundary Rules

When a task is outside a skill's direct wording:

1. Identify which standard interface should own the change: data selection,
   config, pipeline, fit execution, analysis, or summary.
2. Check whether the existing references define that interface.
3. Express the task through the existing interface if possible.
4. Read source code only when the documented interfaces do not define the
   behavior, a command fails with an implementation-level error, or code changes
   are explicitly requested.

Do not bypass these project capabilities:

- `scan-data` for initial dataset discovery.
- `init-config` for full config generation.
- Built-in data loading and averaging.
- Pipeline validation and execution for iterfit.
- `uv run fdtr fit --config <config.toml>` for fitting.

## Reference Selection

Use the focused reference rather than reading source code:

| Need | Read |
| --- | --- |
| Available commands and flags | `references/cli-reference.md` |
| Measurement file formats and averaging semantics | `references/data-formats.md` |
| Layer indexing and parameter fields | `references/parameter-and-layers.md` |
| Config generation workflow | `.claude/skills/fdtr-config/SKILL.md` |
| Custom iterfit pipeline fields | `.claude/skills/fdtr-iterpipeline/SKILL.md` |
| Sensitivity workflow | `.claude/skills/fdtr-sensitivity/SKILL.md` |
| Uncertainty workflow | `.claude/skills/fdtr-uncertainty/SKILL.md` |
