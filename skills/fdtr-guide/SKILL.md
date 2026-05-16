---
name: fdtr-guide
description: Use when starting any FDTR data processing or analysis tasks.
---

# FDTR-guide

Classify the FDTR task, then load only the next needed skill.

## Routing

1. **Data or no data**
- If the user has FDTR data to process: first run  `uv run fdtr scan-data <data_dir>`. ❌**Do not** inspect raw directories or measurement files before scanner discovery.
- Use this first scan output to discover stable `group_key` values and the dataset organization.
- If a group is selected, save its paths spec with:
  `uv run fdtr scan-data <data_dir> --group <group_key> --save`
- If all discovered groups should be processed, save all group path specs with:
  `uv run fdtr scan-data <data_dir> --save-all`
- If no data is involved, do not run `scan-data`.
2. **Config**
- If no existing config is mentioned, load `fdtr-config`.
- `fdtr-config` defines the study structure, layer stack, materials, targets, fixed/fitted parameters, bounds, and full parameter list.
3. **Core function**

   Load only what the user asks for:
- fitting
- sensitivity → `fdtr-sensitivity`
- uncertainty → `fdtr-uncertainty`
4. **Summary**

	Generate a unified report only when requested by `uv run fdtr summary <task_dir>`. Only when explicitly requested to reorganize files and generate report, use `uv run fdtr summary <task_dir> --organize`.

## Index conventions

Layer indexing is 0-based from top to bottom:

- index 0 = transducer
- odd indexes = auto-inserted TBC interfaces
- even indexes after 0 = material layers
- bottom material layer = semi-infinite substrate

Parameter names:

- `Sr_N`, `Sz_N`, `d_N`, `rho_cp_N` refer to layer index `N`
- `TBC_N` refers to the TBC interface layer at index `N`
- `spot_size`, `spot_x`, `spot_y` are beam parameters

## Fit execution

Run only config-driven fits: `uv run fdtr fit --config <config.toml>`.

Before fitting, make sure:

- config exists
- All fit commands always produce PNG + CSV + JSON artifacts. No flags needed to enable output.

Fit strategy:

- `freqfit`: for standard frequency-sweep data at fixed pump–probe offset (usually 0).
- `offsetfit`: for pump–probe beam offset scans at fixed frequency. Usually considered for in-plane/lateral thermal properties.
- `spotfit`: fit spot size from offset scans at a high frequency.

Treat `iterfit` as a pipeline framework. Do not use `iterfit` as a sensitivity strategy.

**Do not** generate pipeline unless requested. To change, load `fdtr-iterpipeline` to generate custom pipeline for iterfit.

## Execution rules

Use default output paths. Do not add ouput path related args unless requested.

By default, after completing a requested FDTR command, do not provide a detailed summary unless the user asks.

All config paths (pipeline, offset_dir, phase_dir, etc.) : absolute paths are used as-is, while relative paths are resolved relative to the config file's parent directory.
