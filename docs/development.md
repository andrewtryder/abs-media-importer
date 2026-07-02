# Development Guide

This guide is for developers looking to modify or contribute to `abs-media-importer`.

## 1. Local Environment Setup

To run the application locally without Docker, install [uv](https://docs.astral.sh/uv/getting-started/installation/) at the version pinned in [`.uv-version`](.uv-version) and sync the development lock file:

```bash
uv venv
uv pip sync requirements-dev.lock
```

Run project tools through the synced virtualenv:

```bash
uv run --no-project pytest
uv run --no-project ruff check .
```

Or run the full CI-equivalent check suite:

```bash
./scripts/check.sh
```

Set `SKIP_DOCKER=1` if you do not want the Docker build smoke test locally (CI skips Docker inside `check.sh` and runs it separately).

### Updating dependencies

When adding or changing dependencies:

1. Edit `requirements.txt` and/or `requirements-dev.txt`
2. Run `./scripts/compile-requirements.sh`
3. Run `uv pip sync requirements-dev.lock`
4. Run `./scripts/check.sh`
5. Commit both source and lock files

---

## 2. Infrastructure Requirements

The application requires a running Redis instance to manage the job queue. You can run Redis locally using Docker:

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

---

## 3. Starting the Application Services

You need to start two processes in separate terminals:

### A. Start the FastAPI Web Server
Configure the local environment variables and start the server using `uvicorn`:

```bash
# Set local environment variables
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=sqlite+aiosqlite:///./app.db
export OUTPUT_ROOT=/tmp/test-podcasts
export WORK_DIR=/tmp/abs_media_importer-work
export DRY_RUN=true  # Set to true to avoid running actual yt-dlp/ffmpeg processes

# Start uvicorn server
uv run --no-project uvicorn app.main:app --reload --port 8080
```

The web interface will be accessible at `http://localhost:8080`.

### B. Start the Background RQ Worker
In a new terminal window, start the worker:

```bash
uv run --no-project rq worker abs_media_importer --url redis://localhost:6379/0
```

---

## 4. Running Tests

The repository includes a comprehensive test suite using `pytest`.

```bash
./scripts/check.sh
```

Or run tests only:

```bash
uv run --no-project pytest
```

---

## 5. Linting and Formatting

The codebase uses `ruff` to enforce code quality and styling consistency.

```bash
uv run --no-project ruff check .
uv run --no-project ruff format --check .

# Auto-format codebase
uv run --no-project ruff format .
```

Pre-commit hooks use the same Ruff version pinned in `requirements-dev.lock`.
