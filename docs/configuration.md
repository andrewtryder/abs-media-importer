# Configuration Reference

`yt-abs-importer` supports flexible configuration using environment variables, a YAML configuration file, or dynamically through the Web UI.

## Configuration Precedence

When the application loads its settings, it resolves them in the following order of precedence (highest priority first):

1. **Environment Variables**: Defined in your `.env` file or host shell environment.
2. **Runtime Settings File**: Dynamic settings saved via the Web UI to `/data/settings.json`.
3. **YAML Config File**: Configuration loaded from `/config/config.yaml`.
4. **Application Defaults**: Built-in defaults.

---

## Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| **Application & Auth** | | |
| `APP_HOST` | `0.0.0.0` | Bind address for the web server. |
| `APP_PORT` | `8080` | Bind port for the web server. |
| `APP_BASE_URL` | — | Public URL used to generate links (optional). |
| `APP_SECRET_KEY` | `changeme-...` | Secret key used for session signing. Required if Auth is enabled. |
| `AUTH_ENABLED` | `false` | Enable HTTP Basic Authentication. Set to `true` if exposing to the LAN/WAN. |
| `AUTH_USERNAME` | — | Username for Basic Authentication. |
| `AUTH_PASSWORD` | — | Password for Basic Authentication. |
| **Infrastructure** | | |
| `REDIS_URL` | `redis://redis:6379/0` | Connection string for Redis queue. |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/app.db` | SQLAlchemy connection string for SQLite database. |
| **Paths & Volumes** | | |
| `HOST_PODCASTS_DIR` | `/mnt/podcasts` | Host path for podcast files (Docker Compose only). |
| `CONTAINER_PODCASTS_DIR` | `/media/podcasts` | Container mount point (Docker Compose only). |
| `OUTPUT_ROOT` | `/media/podcasts` | Path where finished podcasts are written. (Must match Container Path in Docker). |
| `WORK_DIR` | `/data/work` | Workspace for downloading and processing audio. |
| `ARCHIVE_FILE` | `/data/config/youtube-archive.txt` | File where downloaded YouTube IDs are logged. |
| **Download & Processing** | | |
| `ALLOW_PLAYLISTS` | `false` | Allow importing full playlists. |
| `ALLOW_CHANNELS` | `false` | Allow importing full channels. |
| `ALLOW_ARCHIVE_BYPASS` | `false` | Allow re-downloading videos already present in the archive file. |
| `DEFAULT_DESTINATION_FOLDER` | — | Default selected subdirectory under `OUTPUT_ROOT`. |
| `YTDLP_BIN` | `yt-dlp` | Command path to `yt-dlp`. |
| `FFMPEG_BIN` | `ffmpeg` | Command path to `ffmpeg`. |
| `FFPROBE_BIN` | `ffprobe` | Command path to `ffprobe`. |
| `YTDLP_AUDIO_FORMAT` | `m4a` | Format requested from `yt-dlp` (e.g. `m4a`). |
| `YTDLP_AUDIO_QUALITY` | — | Quality arg for `yt-dlp` audio extraction. |
| `YTDLP_EXTRA_ARGS` | — | Space-separated extra arguments passed to `yt-dlp`. |
| `FFMPEG_EXTRA_ARGS` | — | Extra arguments passed to `ffmpeg`. |
| `OUTPUT_EXTENSION` | `m4b` | File extension of the final output file (usually `m4b`). |
| `FILENAME_TEMPLATE` | `{title}.m4b` | Output filename template. |
| `FOLDER_NAME_FIELD` | `uploader_id` | Field used for the folder name (e.g., `uploader_id`, `uploader`, `channel`). |
| `FOLDER_NAME_FALLBACKS` | `uploader_id,channel_id,channel,uploader` | Fallback fields for folder naming. |
| **Job Management** | | |
| `MAX_CONCURRENT_JOBS` | `1` | Maximum number of downloads processed simultaneously. |
| `JOB_TIMEOUT_SECONDS` | `10800` | Job timeout duration in seconds (3 hours). |
| `RETRY_MAX` | `3` | Maximum download retry attempts. |
| `RETRY_INTERVAL_SECONDS` | `60,300,900` | Intervals between retries. |
| `CLEANUP_TEMP_ON_SUCCESS` | `true` | Clean up temporary files in `WORK_DIR` on job success. |
| `CLEANUP_TEMP_ON_FAILURE` | `false` | Clean up temporary files on job failure (useful for debugging). |
| `COLLISION_MODE` | `append_id` | Strategy when output file exists (`skip` \| `overwrite` \| `append_id` \| `append_counter`). |
| **Audiobookshelf Integration** | | |
| `ABS_BASE_URL` | — | Audiobookshelf server URL (e.g. `http://audiobookshelf:13378`). |
| `ABS_API_TOKEN` | — | Audiobookshelf API token. |
| `ABS_LIBRARY_ID` | — | Audiobookshelf Library ID to trigger a scan for. |
| `ABS_SCAN_AFTER_SUCCESS` | `false` | Enable automatic library scan requests after job success. |
| **Development** | | |
| `DRY_RUN` | `false` | If `true`, simulate commands instead of downloading or converting. |

---

## YAML Configuration Example

You can configure settings via a configuration file located at `/config/config.yaml`.

```yaml
app:
  host: "0.0.0.0"
  port: 8080
  auth_enabled: false

paths:
  work_dir: "/data/work"
  archive_file: "/data/config/youtube-archive.txt"
  output_root: "/media/podcasts"

download:
  allow_playlists: false
  allow_channels: false
  audio_format: "m4a"
  filename_template: "{title}.m4b"
  folder_name_field: "uploader_id"

jobs:
  max_concurrent_jobs: 1
  timeout_seconds: 10800
  retry_max: 3
  retry_intervals_seconds: [60, 300, 900]

audiobookshelf:
  base_url: "http://audiobookshelf:13378"
  api_token: "your-token"
  library_id: "your-library-id"
  scan_after_success: true
```
