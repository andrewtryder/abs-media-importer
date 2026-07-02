---
trigger: glob
globs: '**/*.py'
---
# Python Rules

Use uv for dependency management with editable requirements sources and pinned lock files.

- Runtime dependencies: `requirements.txt` → compile to `requirements.lock`
- Development dependencies: `requirements-dev.txt` → compile to `requirements-dev.lock`
- Dev-only tools include pytest, coverage, Ruff, mypy, and pre-commit.

Dependency workflow:

1. Edit `requirements.txt` and/or `requirements-dev.txt`
2. Run `./scripts/compile-requirements.sh`
3. Run `uv pip sync requirements-dev.lock`
4. Commit source and lock files together

Local setup:

```bash
uv venv
source .venv/bin/activate
uv pip sync requirements-dev.lock
```

Preferred checks:

- `ruff format --check .`
- `ruff check .`
- `pytest`
- `coverage run -m pytest && coverage report`

Use Ruff for formatting/linting and pytest for tests when configured.
File patterns determine execution: Python checks apply to `*.py` files when those files exist.

## Related docs

- `docs/profiles.md`
- `docs/code-quality-standards.md`
- `docs/ai-rules-maintenance.md`
- `docs/detection.md`
- `docs/deployment/gcp.md`
