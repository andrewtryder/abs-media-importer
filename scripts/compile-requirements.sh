#!/usr/bin/env bash
# Regenerate pinned lock files from editable requirements sources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/uv-env.sh
source "$ROOT/scripts/uv-env.sh"
require_uv

echo "Compiling requirements.lock from requirements.txt..."
uv pip compile requirements.txt -o requirements.lock \
  --python-version "$PYTHON_VERSION" \
  --no-annotate \
  --custom-compile-command "./scripts/compile-requirements.sh"

echo "Compiling requirements-dev.lock from requirements-dev.txt..."
uv pip compile requirements-dev.txt -o requirements-dev.lock \
  --python-version "$PYTHON_VERSION" \
  --no-annotate \
  --custom-compile-command "./scripts/compile-requirements.sh"

echo "Done. Run 'uv pip sync requirements-dev.lock' to update your local environment."
