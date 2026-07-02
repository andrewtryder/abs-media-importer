#!/usr/bin/env bash
# Verify pinned lock files match editable requirements sources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed." >&2
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

check_lock() {
  local source_file=$1
  local lock_file=$2
  local tmp

  tmp="$(mktemp)"
  uv pip compile "$source_file" -o "$tmp" \
    --python-version "$PYTHON_VERSION" \
    --no-annotate \
    --custom-compile-command "./scripts/compile-requirements.sh" \
    -q

  if ! diff -q "$lock_file" "$tmp" >/dev/null; then
    echo "error: $lock_file is out of date. Run ./scripts/compile-requirements.sh" >&2
    diff -u "$lock_file" "$tmp" || true
    rm -f "$tmp"
    exit 1
  fi

  rm -f "$tmp"
}

check_lock requirements.txt requirements.lock
check_lock requirements-dev.txt requirements-dev.lock

echo "Lock files are up to date."
