# Configuration Reference

`abs-media-importer` supports flexible configuration using environment variables, a YAML configuration file, and the Web UI.

## Configuration Precedence

When the application loads its settings, it resolves them in the following order of precedence (highest priority first):

1. **Environment Variables**: Defined in your `.env` file, Docker, or host shell environment. These **lock** the corresponding field in the Web UI.
2. **YAML Config File**: Configuration loaded from `/config/config.yaml`. These also **lock** their fields when present.
3. **Database Overrides**: Settings saved via the Web UI to the `app_settings` table.
4. **Application Defaults**: Built-in defaults.

If a setting is provided via environment or YAML, the Web UI shows it as read-only with a badge indicating the source.

---

## Web UI Editable Settings

The Settings page is driven by a configuration registry. The following settings can be edited in the UI when not locked by environment or YAML:

| Setting | Env Variable | Description |
| :--- | :--- | :--- |
| Output root | `OUTPUT_ROOT` | Base folder for finished audiobooks |
| Default destination folder | `DEFAULT_DESTINATION_FOLDER` | Default subdirectory under output root |
| Cookies file | `COOKIES_FILE` | Absolute path to a Netscape cookies file for yt-dlp |
| Collision mode | `COLLISION_MODE` | `skip`, `overwrite`, `append_id`, or `append_counter` |
| Output extension | `OUTPUT_EXTENSION` | Final file extension (usually `m4b`) |
| Allowed domains | `ALLOWED_DOMAINS` | Comma-separated permitted hostnames |
| yt-dlp extra args | `YTDLP_EXTRA_ARGS` | Space-separated extra yt-dlp arguments |
| ffmpeg extra args | `FFMPEG_EXTRA_ARGS` | Space-separated extra ffmpeg arguments |
| Filename template | `FILENAME_TEMPLATE` | Output filename template |
| Folder name field | `FOLDER_NAME_FIELD` | Primary metadata field for folder naming |
| Folder name fallbacks | `FOLDER_NAME_FALLBACKS` | Comma-separated fallback fields |
| Job timeout | `JOB_TIMEOUT_SECONDS` | Maximum job runtime in seconds |
| Retry count | `RETRY_MAX` | Maximum retry attempts |
| Retry intervals | `RETRY_INTERVAL_SECONDS` | Comma-separated wait times between retries |
| Cleanup temp on success | `CLEANUP_TEMP_ON_SUCCESS` | Remove temp files after success |
| Cleanup temp on failure | `CLEANUP_TEMP_ON_FAILURE` | Remove temp files after failure |
| Dry run | `DRY_RUN` | Simulate imports without downloading |
| Allow playlist URLs | `ALLOW_PLAYLISTS` | Accept playlist-style URLs and import only the single resolved video (full playlist import is not yet supported). |
| Allow channel URLs | `ALLOW_CHANNELS` | Accept channel-style URLs where yt-dlp can resolve a single item (full channel import is not yet supported). |
| ABS scan after success | `ABS_SCAN_AFTER_SUCCESS` | Trigger Audiobookshelf scan after import |

**Read-only in UI (for now):** `MAX_CONCURRENT_JOBS` until runtime concurrency is fully supported.

**Not editable in UI (secrets / infrastructure):** `AUTH_PASSWORD`, `APP_SECRET_KEY`, `ABS_API_TOKEN`, `EXTENSION_API_TOKEN`, `REDIS_URL`, `DATABASE_URL`, and binary paths.

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
| `ARCHIVE_FILE` | `/data/config/youtube-archive.txt` | `yt-dlp` archive file used as a secondary duplicate guard at download time. |
| `COOKIES_FILE` | — | Absolute path to a Netscape cookies file passed to yt-dlp via `--cookies`. |
| **Download & Processing** | | |
| `ALLOW_PLAYLISTS` | `false` | Accept playlist-style URLs. yt-dlp is always invoked with `--no-playlist`, so only the resolved single video is imported; batch playlist imports are not yet supported. |
| `ALLOW_CHANNELS` | `false` | Accept channel-style URLs. Only a single resolved video is imported; batch channel imports are not yet supported. |
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
| `ALLOWED_DOMAINS` | YouTube hostnames | Comma-separated permitted import domains. |
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
  cookies_file: "/data/config/cookies.txt"
  allowed_domains:
    - youtube.com
    - youtu.be

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
