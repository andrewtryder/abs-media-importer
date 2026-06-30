#!/bin/bash
# ============================================================
# guest-install.sh — Guest VM provisioning for native-vm mode
# ============================================================
set -euo pipefail

# Helper logging
log() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

log "Starting native guest installation..."

# 1. Update and install OS packages
log "Updating package list..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y

log "Installing required packages..."
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    ffmpeg \
    atomicparsley \
    git \
    curl \
    redis-server \
    sqlite3 \
    ca-certificates \
    qemu-guest-agent

# 2. Install latest yt-dlp binary
log "Installing latest yt-dlp binary..."
curl -sL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
chmod a+rx /usr/local/bin/yt-dlp

# 3. Create dedicated system user
if ! getent group yt-abs-importer &>/dev/null; then
    log "Creating yt-abs-importer group..."
    groupadd -r yt-abs-importer
fi

if ! getent passwd yt-abs-importer &>/dev/null; then
    log "Creating yt-abs-importer user..."
    useradd -r -g yt-abs-importer -d /var/lib/yt-abs-importer -s /sbin/nologin -c "yt-abs-importer service user" yt-abs-importer
fi

# 4. Copy app files and set up virtual environment
APP_DIR="/opt/yt-abs-importer"
if [ ! -d "$APP_DIR" ]; then
    log "Cloning repository..."
    git clone https://github.com/andrewtryder/yt-abs-importer.git "$APP_DIR"
else
    log "App directory already exists, checking for latest changes..."
    cd "$APP_DIR"
    git fetch origin || true
fi

cd "$APP_DIR"

log "Creating Python virtual environment..."
python3 -m venv .venv
.venv/bin/pip install --no-cache-dir --upgrade pip
.venv/bin/pip install --no-cache-dir -r requirements.txt

# 5. Create directories
log "Creating config, data, and log directories..."
mkdir -p /etc/yt-abs-importer
mkdir -p /var/lib/yt-abs-importer/work
mkdir -p /var/lib/yt-abs-importer/podcasts
mkdir -p /var/log/yt-abs-importer

# Initialize archive file
touch /etc/yt-abs-importer/youtube-archive.txt

# 6. Configure environment defaults
ENV_FILE="/etc/yt-abs-importer/.env"
if [ ! -f "$ENV_FILE" ]; then
    log "Creating default configuration at $ENV_FILE..."
    cp .env.example "$ENV_FILE"
    
    # Generate random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Update config paths and keys
    sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${SECRET_KEY}|" "$ENV_FILE"
    sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|" "$ENV_FILE"
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:////var/lib/yt-abs-importer/app.db|" "$ENV_FILE"
    sed -i "s|^WORK_DIR=.*|WORK_DIR=/var/lib/yt-abs-importer/work|" "$ENV_FILE"
    sed -i "s|^ARCHIVE_FILE=.*|ARCHIVE_FILE=/etc/yt-abs-importer/youtube-archive.txt|" "$ENV_FILE"
    sed -i "s|^OUTPUT_ROOT=.*|OUTPUT_ROOT=/var/lib/yt-abs-importer/podcasts|" "$ENV_FILE"
    sed -i "s|^YTDLP_BIN=.*|YTDLP_BIN=/usr/local/bin/yt-dlp|" "$ENV_FILE"
    sed -i "s|^FFMPEG_BIN=.*|FFMPEG_BIN=/usr/bin/ffmpeg|" "$ENV_FILE"
    sed -i "s|^FFPROBE_BIN=.*|FFPROBE_BIN=/usr/bin/ffprobe|" "$ENV_FILE"
fi

# 7. Apply permission ownerships
log "Setting file ownership permissions..."
chown -R yt-abs-importer:yt-abs-importer /var/lib/yt-abs-importer
chown -R yt-abs-importer:yt-abs-importer /etc/yt-abs-importer
chown -R yt-abs-importer:yt-abs-importer /var/log/yt-abs-importer
# Virtualenv and app dir owned by root but readable by yt-abs-importer for security
chown -R root:root "$APP_DIR"
chown -R yt-abs-importer:yt-abs-importer "$APP_DIR"

# 8. Deploy systemd services
log "Deploying systemd services..."
cp "$APP_DIR/systemd/yt-abs-importer-app.service" /etc/systemd/system/
cp "$APP_DIR/systemd/yt-abs-importer-worker.service" /etc/systemd/system/

systemctl daemon-reload

log "Enabling services..."
systemctl enable redis-server
systemctl enable yt-abs-importer-app
systemctl enable yt-abs-importer-worker
systemctl enable qemu-guest-agent --now

# Start redis-server if not running
systemctl start redis-server

# Start the application services since safe defaults are written
log "Starting yt-abs-importer services..."
systemctl start yt-abs-importer-app
systemctl start yt-abs-importer-worker

log "Native guest installation completed successfully!"
