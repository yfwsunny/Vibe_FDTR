# FDTR Toolkit

## Skill Architecture

```
skills/
  fdtr-guide/SKILL.md           ← entry point (router)
  fdtr-config/SKILL.md          ← config generation
  fdtr-iterpipeline/SKILL.md    ← pipeline customization
  fdtr-sensitivity/SKILL.md     ← sensitivity analysis
  fdtr-uncertainty/SKILL.md     ← uncertainty analysis
```

| Skill | When to load | What it does |
|---|---|---|
| `fdtr-guide` | Any FDTR-related request | Routes to the right sub-skill |
| `fdtr-config` | Generating or editing a config TOML | Builds layer stack, materials, fit targets via `init-config` |
| `fdtr-iterpipeline` | Customizing iterative fitting steps | Creates pipeline TOML for iterfit |
| `fdtr-sensitivity` | "Which parameters matter?" | Runs sensitivity analysis, recommends fit targets |
| `fdtr-uncertainty` | "How reliable are my results?" | Propagates uncertainties to fitted parameters |

### Trigger Keywords

Load `fdtr-guide` when the user mentions: FDTR, thermal fitting, thermal analysis, data processing, frequency domain thermoreflectance, 热反射, 拟合, 数据分析, 帮我分析.

## Usage Rules

- Unless the user asks to modify code, do not read `src/`
- Skill directory is `skills/` in this repo, or `.claude/skills/` after registration

## Reference Documents

| File | Content |
|---|---|
| `references/cli-reference.md` | All CLI commands and flags |
| `references/layer-conventions.md` | Layer indexing, TBC conventions, TOML examples |
| `references/data-formats.md` | Data file formats (offset-scan / freq-sweep) |
| `references/parameter-naming.md` | Parameter naming (Sr_N, Sz_N, d_N, etc.) |
