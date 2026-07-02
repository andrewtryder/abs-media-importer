---
targets: ["*"]
description: "Python standards"
globs: ["**/*.py"]
---

# Python Rules

Use uv for dependency management with editable requirements sources and pinned lock files.

- Runtime dependencies: `requirements.txt` → compile to `requirements.lock`
- Development dependencies: `requirements-dev.txt` → compile to `requirements-dev.lock`
- Dev-only tools include pytest, coverage, Ruff, mypy, and pre-commit.
- Pin uv to the version in `.uv-version` (must match CI).

Dependency workflow:

1. Edit `requirements.txt` and/or `requirements-dev.txt`
2. Run `./scripts/compile-requirements.sh`
3. Run `uv pip sync requirements-dev.lock`
4. Commit source and lock files together

Local setup:

```bash
uv venv
uv pip sync requirements-dev.lock
```

Before opening a PR, run the same checks as CI:

```bash
./scripts/check.sh
```

Use `uv run --no-project <tool>` when running individual commands outside `./scripts/check.sh`.

Preferred checks (via `./scripts/check.sh`):

- Lock freshness (`scripts/check-requirements-lock.sh`)
- `ruff format --check .`
- `ruff check .`
- `mypy app worker`
- `pytest`

Use Ruff for formatting/linting and pytest for tests when configured.
File patterns determine execution: Python checks apply to `*.py` files when those files exist.

## Related docs

- `docs/profiles.md`
- `docs/code-quality-standards.md`
- `docs/ai-rules-maintenance.md`
- `docs/detection.md`
- `docs/deployment/gcp.md`
