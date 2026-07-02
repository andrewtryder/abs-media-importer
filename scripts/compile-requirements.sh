#!/usr/bin/env bash
# Regenerate pinned lock files from editable requirements sources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed." >&2
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

echo "Compiling requirements.lock from requirements.txt..."
uv pip compile requirements.txt -o requirements.lock \
  --custom-compile-command "./scripts/compile-requirements.sh"

echo "Compiling requirements-dev.lock from requirements-dev.txt..."
uv pip compile requirements-dev.txt -o requirements-dev.lock \
  --custom-compile-command "./scripts/compile-requirements.sh"

echo "Done. Run 'uv pip sync requirements-dev.lock' to update your local environment."
