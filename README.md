# AI Educational Product Factory

A subject-agnostic system that transforms a learner problem into a complete, evidence-aware, verifiable educational product.

## What It Does

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

MIT
