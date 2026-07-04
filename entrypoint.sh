#!/bin/bash
# ============================================================
# entrypoint.sh — PUID/PGID remapping + service startup
# ============================================================
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting reeldock"
echo "  PUID=$PUID  PGID=$PGID"

# Create group/user if they don't match existing
if ! getent group appgroup &>/dev/null; then
    groupadd -g "$PGID" appgroup 2>/dev/null || true
fi
if ! getent passwd appuser &>/dev/null; then
    useradd -u "$PUID" -g "$PGID" -M -s /bin/bash appuser 2>/dev/null || true
fi

# Ensure data subdirectories exist (host bind mount may replace /data without them)
mkdir -p /data/work /data/logs /data/config

# Fix ownership of data directories
chown -R "$PUID:$PGID" /data /config 2>/dev/null || true

MODE=${1:-app}

case "$MODE" in
  app|worker)
    echo "Running startup preflight checks..."
    gosu "$PUID:$PGID" python -m app.preflight || exit 1
    ;;
esac

case "$MODE" in
  app)
    echo "Starting FastAPI app..."
    exec gosu "$PUID:$PGID" python -m uvicorn app.main:app \
      --host "${APP_HOST:-0.0.0.0}" \
      --port "${APP_PORT:-8080}" \
      --no-access-log
    ;;
  worker)
    echo "Starting RQ worker..."
    export RQ_REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
    exec gosu "$PUID:$PGID" python -m rq.cli worker reeldock
    ;;
  *)
    exec gosu "$PUID:$PGID" "$@"
    ;;
esac
