# Development Guide

This guide is for developers looking to modify or contribute to `abs-media-importer`.

## 1. Local Environment Setup

To run the application locally without Docker, set up a Python virtual environment and install the development dependencies:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development packages
pip install -r requirements-dev.txt
```

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
uvicorn app.main:app --reload --port 8080
```

The web interface will be accessible at `http://localhost:8080`.

### B. Start the Background RQ Worker
In a new terminal window with the virtual environment active, start the worker:

```bash
# Start background worker
rq worker abs_media_importer --url redis://localhost:6379/0
```

---

## 4. Running Tests

The repository includes a comprehensive test suite using `pytest`.

Ensure your virtual environment is active, then run:

```bash
pytest
```

---

## 5. Linting and Formatting

The codebase uses `ruff` to enforce code quality and styling consistency.

```bash
# Run code check and linting
ruff check .

# Check formatting
ruff format --check .

# Auto-format codebase
ruff format .
```
