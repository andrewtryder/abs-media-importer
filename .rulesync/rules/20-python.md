---
targets: ["*"]
description: "Python standards"
globs: ["**/*.py"]
---

# Python Rules

Use uv project mode with dependencies declared in `pyproject.toml` and locked in `uv.lock`.

- Runtime dependencies: `[project.dependencies]`
- Development dependencies: `[dependency-groups].dev`

Dependency workflow:

1. Edit dependencies in `pyproject.toml`
2. Run `uv lock`
3. Run `uv sync --dev`
4. Commit `pyproject.toml` and `uv.lock` together

Local setup:

```bash
uv sync --dev
```

Before opening a PR, run the same checks as CI:

```bash
uv sync --locked --dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy app worker
uv run --frozen pytest
```

Use Ruff for formatting/linting and pytest for tests when configured.
File patterns determine execution: Python checks apply to `*.py` files when those files exist.

## Related docs

- `docs/profiles.md`
- `docs/code-quality-standards.md`
- `docs/ai-rules-maintenance.md`
- `docs/detection.md`
- `docs/deployment/gcp.md`
