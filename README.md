# abs-media-importer

<p align="center">
  <img src="assets/abs-media-importer-icon.svg" alt="abs-media-importer Icon" width="240" />
</p>

A self-hosted sidecar application that converts individual YouTube videos into `.m4b` audiobook files and writes them directly to the directory that [Audiobookshelf](https://www.audiobookshelf.org/) scans.

> [!NOTE]
> **This is not an Audiobookshelf plugin.** It is an independent container that shares the same podcast/audiobook directory as your Audiobookshelf instance.

---

## What It Does / Workflow

1. Paste a YouTube video URL into the web UI.
2. The app fetches metadata (title, channel, duration, chapters) using `yt-dlp`.
3. Select the destination folder inside your Audiobookshelf podcasts directory (or create a new folder).
4. Optionally edit the output title and select embed options (metadata, chapters, thumbnail).
5. Submit — a background worker downloads the audio with `yt-dlp` and remuxes it to `.m4b` using `ffmpeg` (with cover art and chapter markings).
6. The finished `.m4b` is written to your Audiobookshelf media directory.
7. Optionally trigger an Audiobookshelf library scan automatically via API.

---

## Features

- **Metadata Preview**: Review thumbnail, title, channel name, and chapters before downloading.
- **Background Downloads**: Async task queue managed by an RQ worker with live-updating log views.
- **Embedded Media**: Automatically embeds cover art, metadata, and chapter divisions into the `.m4b` file.
- **Audiobookshelf Integration**: Automatically triggers library scans via API upon successful download.
- **Path Traversal Protection**: Secure validation prevents writing outside of the designated root directory.
- **Format Fallbacks**: Gracefully falls back to audio-only if cover art muxing fails.
- **Collision Management**: Configurable options for duplicate filenames (`skip`, `overwrite`, `append_id`, `append_counter`).
- **NFS & Permissions Friendly**: Supports `PUID` and `PGID` configurations to match host filesystem ownership.

---

## Quick Start (Docker Compose)

Deploy the application stack in minutes:

```bash
# 1. Clone the repository
git clone https://github.com/andrewtryder/abs-media-importer.git
cd abs-media-importer

# 2. Configure paths in .env
cp .env.example .env
# Edit .env to set your HOST_PODCASTS_DIR (e.g. /mnt/podcasts)

# 3. Create local storage directories
mkdir -p data config

# 4. Start the application
docker compose up -d
```

The web interface will be available at **`http://localhost:8080`** (localhost only by default).

For a complete walkthrough, see the [Quickstart Guide](docs/quickstart.md).

---

## Rename Migration Notice

Recent releases finalized the project rename to `abs-media-importer`.

- Update clone/remotes to `github.com/andrewtryder/abs-media-importer`.
- Rename any leftover local paths/service names/images to `abs-media-importer`.
- Reinstall the Firefox extension if you were using the previous extension ID.
- If you automate extension API auth, use `ABS_MEDIA_IMPORTER_*` and `X-ABS-MEDIA-IMPORTER-Token`.
- If you use native/systemd deployments, migrate queue/service identifiers to `abs_media_importer` and `abs-media-importer-*`.

---

## Path Model Summary

When deployed under Docker, paths map from the Docker host to the container:

* **`HOST_PODCASTS_DIR`**: The directory on your Docker host machine where podcasts/audiobooks are stored.
* **`CONTAINER_PODCASTS_DIR`**: The path inside the running container (usually `/media/podcasts`).
* **`OUTPUT_ROOT`**: The path the application writes to inside the container. This must match `CONTAINER_PODCASTS_DIR`.

> [!IMPORTANT]
> In Docker, the application writes to the **container path**, not the host path. The Settings page in the web UI should normally be left as `/media/podcasts`.

### Common Configuration Examples

#### Mac Docker Test
For local testing on macOS where a network share is mounted under `/Volumes`:
```env
HOST_PODCASTS_DIR=/Volumes/Synology/Media/Podcasts
CONTAINER_PODCASTS_DIR=/media/podcasts
OUTPUT_ROOT=/media/podcasts
```

#### Proxmox / Linux Docker
For a standard Linux server mounting an NFS share locally:
```env
HOST_PODCASTS_DIR=/mnt/podcasts
CONTAINER_PODCASTS_DIR=/media/podcasts
OUTPUT_ROOT=/media/podcasts
```

For more details on volume setups, read the [Paths and Volumes Guide](docs/paths-and-volumes.md).

---

## Screenshots

Screenshots are coming soon. Recommended captures:
- Import page
- Preview page
- Jobs page
- Job detail page
- Settings page

---

## Detailed Documentation

Refer to the documents in the `/docs` directory for detailed deployment and configuration topics:

* 📖 **[Quickstart Guide](docs/quickstart.md)**: Setup and initial configuration instructions.
* 📁 **[Paths and Volumes](docs/paths-and-volumes.md)**: Deep dive into the host-to-container volume model.
* ⚙️ **[Configuration Reference](docs/configuration.md)**: Full list of environment variables and YAML settings.
* 🐋 **[Docker Deployment](docs/deployment-docker.md)**: Managing the Docker Compose stack, Mac file sharing, and write validation.
* 🖥️ **[Proxmox VE Deployment](docs/deployment-proxmox.md)**: Virtual Machine (Docker/Native) and Linux Container (LXC) setups.
* 📚 **[Audiobookshelf Integration](docs/audiobookshelf.md)**: Connecting ABS, directory naming layout, and scan API configuration.
* 🛠️ **[Troubleshooting Guide](docs/troubleshooting.md)**: Fixes for permission errors, extractor issues, and missing metadata.
* 🔒 **[Security Guidelines](docs/security.md)**: Localhost binding, Basic Auth configuration, and reverse proxying.
* 💻 **[Development Guide](docs/development.md)**: Setting up a local virtual environment, starting Redis, running tests, and linting.
* 🚀 **[Releasing Guide](docs/releasing.md)**: Release Please workflow, component-based version bumps, and extension asset publishing.

---

## Development

To run tests and code quality checks locally:

```bash
# Set up virtual environment and dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Run pytest suite
pytest

# Check code formatting and linting
ruff check .
ruff format --check .
```

See the [Development Guide](docs/development.md) for full instructions.
