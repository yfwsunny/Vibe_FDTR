# Vibe-FDTR

AI agent skills for Frequency Domain Thermoreflectance (FDTR) data analysis.

Vibe-FDTR gives any AI agent the ability to perform thermal-property fitting, sensitivity analysis, and uncertainty quantification on FDTR measurements — through natural language conversation. The agent handles config generation, CLI execution, and result interpretation; you just describe what you want.

## How It Works

The agent follows a guided workflow:

```
You describe the task → fdtr-guide routes → sub-skill executes → results returned
```

1. **fdtr-guide** (entry point) classifies your task and loads the right sub-skill
2. The sub-skill walks the agent through config generation, fitting, or analysis
3. The agent runs CLI commands and presents results in plain language

## Skills

| Skill | When it triggers | What it does |
|---|---|---|
| **fdtr-guide** | Any FDTR-related request | Routes to the right sub-skill |
| **fdtr-config** | Generating or editing a config TOML | Builds the layer stack, materials, fit targets via `init-config` |
| **fdtr-iterpipeline** | Customizing iterative fitting steps | Creates pipeline TOML defining the step sequence for iterfit |
| **fdtr-sensitivity** | "Which parameters matter?" | Runs model-based sensitivity analysis, recommends fit targets |
| **fdtr-uncertainty** | "How reliable are my results?" | Propagates known uncertainties to fitted parameters |

### Typical conversation

| You say | Agent does |
|---|---|
| "I have FDTR data in `./Data`, fit Sz and TBC for Gold on Graphite" | `scan-data` → `init-config` → confirm config → `fit` → present results |
| "Which parameters should I fit?" | Loads `fdtr-sensitivity`, runs sensitivity curves, recommends targets |
| "What's the uncertainty on S_2?" | Loads `fdtr-uncertainty`, computes coupled isotropic conductivity uncertainty |
| "Customize my iterfit pipeline to fit spot first, then Sr" | Loads `fdtr-iterpipeline`, generates custom pipeline TOML |

## Installation

### 1. Install the CLI

```bash
git clone https://github.com/yfwsunny/Vibe_FDTR.git
cd Vibe_FDTR
uv sync
```

Verify: `uv run fdtr --help`

### 2. Register skills with your agent

**Claude Code** — copy or symlink into your project's `.claude/skills/`:

```bash
mkdir -p .claude/skills
cp -r skills/* .claude/skills/
```

**Other agents** (Hermes, Codex, generic) — see [AGENTS.md](AGENTS.md) for per-agent instructions.

## What the Agent Can Do

Through the skills, the agent can:

- **Scan** data directories and auto-discover measurement groups
- **Generate** TOML configs with correct layer stacks, materials, and fit bounds
- **Fit** thermal parameters (conductivity, TBC, thickness, spot size) using four strategies:
  - `freqfit` — frequency-sweep at fixed offset
  - `offsetfit` — beam-offset scans at fixed frequency
  - `spotfit` — FWHM beam-spot estimation
  - `iterfit` — multi-step iterative pipeline
- **Analyze** parameter sensitivity to guide experiment design
- **Quantify** uncertainty propagation from known input errors
- **Summarize** results as Markdown reports with plots

## What's New in v0.3

- **Isotropic symmetry support**: Materials with equal in-plane and cross-plane conductivity now use `S = value` instead of separate `Sr`/`Sz`. The CLI auto-converts isotropic materials and supports `fit_S` for coupled conductivity fitting.
- **Symmetry-aware pipeline**: `init-pipeline --config <toml>` generates pipeline steps that match the material symmetry of the base config.
- **Material library enhancements**: `list-materials` now shows symmetry info; `show-material` reports whether a material is isotropic or anisotropic at a given temperature.
- **Config-only fitting**: `fdtr fit` now requires `--config`; direct-arg invocation has been removed for a cleaner interface.

## Skill Architecture

```
skills/                        ← agent-agnostic skill definitions
  fdtr-guide/SKILL.md          ← entry point (load this first)
  fdtr-config/SKILL.md         ← config generation
  fdtr-iterpipeline/SKILL.md   ← pipeline customization
  fdtr-sensitivity/SKILL.md    ← sensitivity analysis
  fdtr-uncertainty/SKILL.md    ← uncertainty analysis

.claude/skills/                ← Claude Code registration target
references/                    ← shared conventions
examples/                      ← TOML config examples
src/fdtr/                      ← Python CLI engine
```

All skills assume the `fdtr` CLI is installed and accessible via `uv run fdtr`.

## Reference Documents

Skills delegate detailed conventions to shared references:

- `references/cli-reference.md` — complete CLI command and flag reference
- `references/data-formats.md` — data file format specs
- `references/parameter-naming.md` — parameter naming (`Sr_N`, `Sz_N`, `TBC_N`, etc.)
- `references/layer-conventions.md` — layer indexing and TBC conventions

## License

MIT. See [LICENSE](LICENSE).
