#!/usr/bin/env bash
# Run the same quality checks as CI (optionally skipping Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/uv-env.sh
source "$ROOT/scripts/uv-env.sh"
require_uv

SKIP_DOCKER="${SKIP_DOCKER:-0}"

echo "Checking lock files..."
./scripts/check-requirements-lock.sh

echo "Syncing development environment..."
ensure_venv

echo "Running Ruff check..."
run_tool ruff check .

echo "Running Ruff format check..."
run_tool ruff format --check .

echo "Running Mypy..."
run_tool mypy app worker

echo "Running tests..."
run_tool pytest

if [[ "$SKIP_DOCKER" != "1" ]]; then
  echo "Running Docker build smoke test..."
  docker build .
fi

echo "All checks passed."
