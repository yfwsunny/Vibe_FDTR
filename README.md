# Vibe-FDTR

AI agent skills for Frequency Domain Thermoreflectance (FDTR) data analysis.

Vibe-FDTR gives any AI agent the ability to perform thermal-property fitting, sensitivity analysis, and uncertainty quantification on FDTR measurements through natural language conversation. The agent handles config generation, CLI execution, and result interpretation; you just describe what you want.

## How It Works

The agent follows a guided workflow:

```text
You describe the task -> CLAUDE.md routes -> task-specific skill executes -> results returned
```

1. **CLAUDE.md** classifies the task and loads only the next needed skill.
2. The task-specific skill walks the agent through config generation, fitting, or analysis.
3. The agent runs CLI commands and presents results in plain language.

## Skills

| Skill | When it triggers | What it does |
| --- | --- | --- |
| **fdtr-config** | Generating or editing a config TOML | Builds the layer stack, materials, fit targets via `init-config` |
| **fdtr-expert** | Expert diagnosis or strategy requests | Reviews data quality, fitting schemes, and experiment design choices |
| **fdtr-iterpipeline** | Customizing iterative fitting steps | Creates pipeline TOML defining the step sequence for iterfit |
| **fdtr-sensitivity** | "Which parameters matter?" | Runs model-based sensitivity analysis, recommends fit targets |
| **fdtr-uncertainty** | "How reliable are my results?" | Propagates known uncertainties to fitted parameters |

### Typical Conversation

| You say | Agent does |
| --- | --- |
| "I have FDTR data in `./Data`, fit Sz and TBC for Gold on Graphite" | `scan-data` -> `init-config` -> confirm config -> `fit` -> present results |
| "Which parameters should I fit?" | Loads `fdtr-sensitivity`, runs sensitivity curves, recommends targets |
| "What's the uncertainty on Sz_2?" | Loads `fdtr-uncertainty`, computes propagation from known uncertainties |
| "Customize my iterfit pipeline to fit spot first, then Sr" | Loads `fdtr-iterpipeline`, generates custom pipeline TOML |

## Installation

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### 1. Install the CLI

```bash
git clone https://github.com/yfwsunny/Vibe_FDTR.git
cd Vibe_FDTR
uv sync
```

Verify:

```bash
uv run fdtr list-materials
uv run fdtr --help
```

### 2. Configure Your Agent

This release keeps skill definitions under `.claude/skills/<name>/SKILL.md`. Shared references are in `references/`, and examples are in `examples/`.

**Claude Code**

- Use `CLAUDE.md` as the canonical project-agent entry point.
- Ensure the runtime can expose repo-local skills to the Skill tool.
- If the runtime reports an unknown skill, read the matching `.claude/skills/<name>/SKILL.md` file directly as fallback.

**OpenCode**

- Add the `.claude/skills` directory to your agent's instructions configuration.

**Other agents** (Hermes, Codex, generic)

- Start from [AGENTS.md](AGENTS.md).
- If your runtime does not auto-register skills, load `CLAUDE.md` first and then read individual `.claude/skills/<name>/SKILL.md` files on demand.

## What the Agent Can Do

Through the skills, the agent can:

- **Scan** data directories and auto-discover measurement groups
- **Generate** TOML configs with correct layer stacks, materials, and fit bounds
- **Fit** thermal parameters (conductivity, TBC, thickness, spot size) using four strategies:
  - `freqfit` - frequency-sweep at fixed offset
  - `offsetfit` - beam-offset scans at fixed frequency
  - `spotfit` - FWHM beam-spot estimation
  - `iterfit` - multi-step iterative pipeline
- **Analyze** parameter sensitivity to guide experiment design
- **Quantify** uncertainty propagation from known input errors
- **Summarize** results as Markdown reports with plots

## Skill Architecture

```text
CLAUDE.md                      -> canonical agent workflow
AGENTS.md                      -> compatibility entry point for non-Claude agents
.claude/skills/
  fdtr-config/SKILL.md         -> config generation
  fdtr-iterpipeline/SKILL.md   -> pipeline customization
  fdtr-sensitivity/SKILL.md    -> sensitivity analysis
  fdtr-uncertainty/SKILL.md    -> uncertainty analysis

references/                    -> shared conventions
examples/                      -> TOML config examples
src/fdtr/                      -> Python CLI engine
```

All skills assume the `fdtr` CLI is installed and accessible via `uv run fdtr`.

## Reference Documents

Skills delegate detailed conventions to shared references:

- `references/cli-reference.md` - complete CLI command and flag reference
- `references/data-formats.md` - data file format specs
- `references/parameter-and-layers.md` - supplementary fit fields and TOML examples (core rules inlined in CLAUDE.md)

## License

MIT. See [LICENSE](LICENSE).
