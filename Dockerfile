# ============================================================
# abs-media-importer — Dockerfile
# ============================================================
# Python 3.12-slim base with yt-dlp, ffmpeg, and app deps.
# Supports PUID/PGID for volume permissions via entrypoint.sh
# ============================================================

FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="abs-media-importer"
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
ENV UV_SYSTEM_PYTHON=1
COPY requirements.lock .
RUN uv pip sync requirements.lock

# ── Final image ─────────────────────────────────────────────
FROM base AS final

WORKDIR /app

# Copy installed Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ app/
COPY worker/ worker/
COPY pyproject.toml .

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
ENV PATH="/usr/local/bin:$PATH"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:8080/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
