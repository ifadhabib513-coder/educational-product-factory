# AI Educational Product Factory

A subject-agnostic system that transforms a learner problem into a complete, evidence-aware, verifiable educational product.

## What It Is Intended To Do

Given a subject, topic, learner profile, and problem description, the factory generates:

- Product specification and learning objectives
- Curriculum blueprint
- Lessons and explanations
- Worked examples and practice questions
- Assessments with answer keys and rubrics
- Visual diagrams and illustrations
- Verification and quality reports

## What It Does NOT Do

- Claim to be AGI or production-ready
- Replace human educators
- Guarantee scientific accuracy without human review
- Execute arbitrary code from LLM output

## Quick Start

```bash
pip install -e ".[dev]"
lpf --help
```

## Writer Model Providers

`lpf generate` chooses the writer that writes the lessons:

| `--model` / `LPF_PROVIDER` | Endpoint                       | Needs API key | Typical model |
|----------------------------|--------------------------------|---------------|---------------|
| `mock` (default)           | none (deterministic, offline)  | no            | —             |
| `openai-compatible`        | `LPF_MODEL_ENDPOINT` (e.g. `https://api.openai.com/v1`) | `LPF_API_KEY` | `gpt-4o-mini` |
| `ollama`                   | `LPF_MODEL_ENDPOINT` (e.g. `http://localhost:11434`)       | no            | `llama3.2`    |

```bash
lpf generate Physics "Projectile Motion"                 # offline mock, byte-identical
lpf generate Physics "Projectile Motion" --model ollama  # local Ollama
LPF_PROVIDER=openai-compatible LPF_MODEL_ENDPOINT=... lpf generate Physics "..." --model ollama
```

- **Offline `mock` is the default and the safe path**: it needs no network, no
  keys, and produces reproducible output. Live providers are opt-in per run.
- A CLI `--model` **flag overrides** `LPF_PROVIDER`, which overrides an
  optional `lpf.toml` in the working directory:

  ```toml
  [model]
  kind = "ollama"            # mock | openai-compatible | ollama
  name = "llama3.2"          # LPF_MODEL_NAME
  endpoint = "http://localhost:11434"  # LPF_MODEL_ENDPOINT
  api_key = ""               # LPF_API_KEY
  [run]
  output_dir = "projects"    # LPF_OUTPUT_DIR
  ```

- Unknown kinds fail the run with a readable message rather than silently
  falling back to a live provider.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
ruff format --check src/ tests/
```

## Status

Pre-alpha. Stage 1 complete (project foundation). See `docs/ROADMAP.md` for progress.

## License

**Proprietary — all rights reserved.** This project is private and is not open
source. No rights are granted to copy, modify, distribute, or otherwise use any
part of it. Distributions declare `LicenseRef-Proprietary`.
