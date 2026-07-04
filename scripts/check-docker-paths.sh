#!/usr/bin/env bash
# ============================================================
# check-docker-paths.sh — validate HOST_PODCASTS_DIR before compose up
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

load_env() {
    if [[ -f "$REPO_ROOT/.env" ]]; then
        # shellcheck disable=SC1091
        set -a
        source "$REPO_ROOT/.env"
        set +a
    fi
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [HOST_PODCASTS_DIR]

Validate that the podcast output directory exists and is writable on the host
before running docker compose up.

If HOST_PODCASTS_DIR is omitted, the value from .env (or /mnt/podcasts) is used.
EOF
}

print_mac_hints() {
    cat <<EOF
macOS tips:
  - Mount the network share first (Finder -> Connect to Server)
  - Ensure the path exists: ls -la "$HOST_PODCASTS_DIR"
  - Docker Desktop -> Settings -> Resources -> File sharing -> add /Volumes
EOF
}

print_puid_hint() {
    local puid="${PUID:-1000}"
    local pgid="${PGID:-1000}"
    cat <<EOF
Inside the container, files are written as UID:GID ${puid}:${pgid}.
If the host directory is writable for you but imports fail, set PUID/PGID in .env
to match the directory owner. See docs/paths-and-volumes.md.
EOF
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        usage
        exit 0
    fi

    load_env
    HOST_PODCASTS_DIR="${1:-${HOST_PODCASTS_DIR:-/mnt/podcasts}}"

    echo "Checking HOST_PODCASTS_DIR: $HOST_PODCASTS_DIR"

    if [[ ! -e "$HOST_PODCASTS_DIR" ]]; then
        echo "ERROR: Directory does not exist: $HOST_PODCASTS_DIR" >&2
        echo "Docker Compose will not auto-create this path (create_host_path: false)." >&2
        if [[ "$HOST_PODCASTS_DIR" == /Volumes/* ]]; then
            echo >&2
            print_mac_hints >&2
        fi
        exit 1
    fi

    if [[ ! -d "$HOST_PODCASTS_DIR" ]]; then
        echo "ERROR: Path exists but is not a directory: $HOST_PODCASTS_DIR" >&2
        exit 1
    fi

    test_file="$HOST_PODCASTS_DIR/.reeldock-write-test"
    if ! touch "$test_file" 2>/dev/null; then
        echo "ERROR: Directory is not writable: $HOST_PODCASTS_DIR" >&2
        print_puid_hint >&2
        exit 1
    fi
    rm -f "$test_file"

    echo "OK: $HOST_PODCASTS_DIR exists and is writable on the host."
    print_puid_hint
}

main "$@"
