# Installing FDTR Skills for AI Agents

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## Install the CLI

```bash
git clone <repo-url>
cd Vibe_FDTR_publish3
uv sync
```

Verify:

```bash
uv run fdtr list-materials
uv run fdtr --help
```

## Register Skills with Your Agent

Skills are in the `skills/` directory. The entry point is `skills/fdtr-guide/SKILL.md`.

### Claude Code

Copy or symlink skill directories into your project's `.claude/skills/`:

```bash
mkdir -p .claude/skills
cp -r /path/to/Vibe_FDTR_publish3/skills/* .claude/skills/
```

For development (live-editing):

```bash
mkdir -p .claude/skills
ln -s /path/to/Vibe_FDTR_publish3/skills/fdtr-guide      .claude/skills/fdtr-guide
ln -s /path/to/Vibe_FDTR_publish3/skills/fdtr-config      .claude/skills/fdtr-config
ln -s /path/to/Vibe_FDTR_publish3/skills/fdtr-iterpipeline .claude/skills/fdtr-iterpipeline
ln -s /path/to/Vibe_FDTR_publish3/skills/fdtr-sensitivity  .claude/skills/fdtr-sensitivity
ln -s /path/to/Vibe_FDTR_publish3/skills/fdtr-uncertainty  .claude/skills/fdtr-uncertainty
```

See `CLAUDE.md` for Claude Code runtime behavior.

### Hermes

Point Hermes at the `skills/` directory as the skill root. Ensure the runtime can read `SKILL.md` files from subdirectories.

### Codex / OpenAI Agents

Read skill files directly from `skills/<name>/SKILL.md`. Start with `skills/fdtr-guide/SKILL.md`, then follow the routing instructions to load sub-skills.

### Generic File-Based Agents

Load `skills/fdtr-guide/SKILL.md` as the entry prompt. When the skill instructs to "load fdtr-config" (or another sub-skill), read the corresponding `skills/<name>/SKILL.md` file and append it to context.

## Usage

Tell your AI agent what you want to do. Examples:

- "I have FDTR data in `./Data`, fit Sz and TBC for Gold on Graphite"
- "Fit thermal conductivity from frequency-sweep data"
- "Generate a sensitivity analysis for my sample"
- "What's the uncertainty on S_2?"
- "自动分析这组数据"

The AI will load the appropriate skill and guide you through the process.
