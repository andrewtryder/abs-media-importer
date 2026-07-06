# ============================================================
# reeldock — Dockerfile
# ============================================================
# Python 3.12-slim base with yt-dlp, ffmpeg, and app deps.
# Supports PUID/PGID for volume permissions via entrypoint.sh
# ============================================================

FROM python:3.14-slim AS base

LABEL org.opencontainers.image.title="reeldock"
LABEL org.opencontainers.image.description="YouTube to Audiobookshelf importer"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    atomicparsley \
    curl \
    wget \
    ca-certificates \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (latest stable binary)
RUN curl -sL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# ── Python dependencies ─────────────────────────────────────
FROM base AS deps

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# ── Final image ─────────────────────────────────────────────
FROM base AS final

WORKDIR /app

# Copy installed Python environment from deps stage
COPY --from=deps /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY app/ app/
COPY worker/ worker/
COPY pyproject.toml .

# Register package metadata so importlib.metadata.version() works at runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv pip install --python /app/.venv/bin/python --no-deps .

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create directories (permissions set at runtime via PUID/PGID)
RUN mkdir -p /data /data/work /data/logs /data/config /media/podcasts /config

# Default environment
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8080
ENV REDIS_URL=redis://redis:6379/0
ENV DATABASE_URL=sqlite+aiosqlite:////data/app.db
ENV WORK_DIR=/data/work
ENV ARCHIVE_FILE=/data/config/youtube-archive.txt
ENV OUTPUT_ROOT=/media/podcasts
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:8080/ready || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
