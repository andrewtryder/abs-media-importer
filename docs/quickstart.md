# Quickstart Guide

This guide will walk you through setting up `abs-media-importer` using Docker Compose.

## 1. Prerequisites

Ensure you have Docker and Docker Compose v2 installed on your system.

## 2. Clone the Repository

```bash
git clone https://github.com/andrewtryder/abs-media-importer.git
cd abs-media-importer
```

## 3. Configure the Environment

Copy the example environment file to `.env`:

```bash
cp .env.example .env
```

Open `.env` in a text editor and set `HOST_PODCASTS_DIR` to the directory on your host machine that Audiobookshelf scans for podcasts:

```env
# Path on your Docker host (Mac or Linux)
HOST_PODCASTS_DIR=/mnt/podcasts
```

*(Optional)* If you need to restrict permissions or configure Audiobookshelf scan triggers, configure those variables in `.env` as well. See [Configuration Guide](configuration.md) for details.

## 4. Create Necessary Directories

Ensure the local storage directories for database files and configuration exist on the host:

```bash
mkdir -p data config
```

## 5. Start the Application

Start the Docker Compose stack in detached mode:

```bash
docker compose up -d
```

This will pull the required images, build the custom application/worker container, and start the stack.

## 6. Access the Application

Verify that the application is running by visiting:

**`http://localhost:8080`**

*(Note: By default, the application binds only to localhost for security. See the [Security Guide](security.md) for details on exposing the app to your local network.)*
