#!/usr/bin/env bash
# Shared uv/Python versions for local scripts and CI parity.

if [[ -z "${REQUIRED_UV_VERSION:-}" && -f .uv-version ]]; then
  REQUIRED_UV_VERSION="$(tr -d '[:space:]' < .uv-version)"
fi

REQUIRED_UV_VERSION="${REQUIRED_UV_VERSION:-0.11.26}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

require_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is not installed." >&2
    echo "Install uv ${REQUIRED_UV_VERSION}: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
  fi

  local actual
  actual="$(uv --version | awk '{print $2}')"
  if [[ "$actual" != "${REQUIRED_UV_VERSION}"* ]]; then
    echo "error: uv ${REQUIRED_UV_VERSION} required; found ${actual}." >&2
    echo "Install the pinned version to match CI: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
  fi
}

run_tool() {
  uv run --no-project "$@"
}

ensure_venv() {
  if [[ ! -d .venv ]]; then
    uv venv
  fi
  uv pip sync requirements-dev.lock
}
