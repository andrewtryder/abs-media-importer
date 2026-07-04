# Docker Deployment Guide

This guide details how to deploy `reeldock` using Docker Compose, verify your configuration, and troubleshoot volume access issues.

## 1. Setup

Follow the steps in the [Quickstart Guide](quickstart.md) to set up your `.env` file and basic directory structures.

### Docker Desktop for Mac (Important)
If you are running Docker Desktop on macOS and mounting network shares (like a Synology NAS or external drive mounted under `/Volumes`), you must ensure Docker has permission to access these paths.
1. Open **Docker Desktop Settings**.
2. Go to **Resources** -> **File sharing**.
3. Add `/Volumes` (or the specific path to your network share) to the list of shared directories.
4. Click **Apply & restart**.

---

## 2. Docker Compose Commands Reference

Here are the most common Docker Compose commands used to manage the application stack:

```bash
# Start the stack in the background
docker compose up -d

# Stop the stack
docker compose down

# Rebuild and restart the stack (useful after updates)
docker compose up --build -d

# View live application logs
docker compose logs -f app

# View live worker logs
docker compose logs -f worker
```

---

## 3. Configuration Verification

Before submitting jobs, verify that Docker Compose parses your `.env` file and maps volumes correctly:

```bash
docker compose config
```

Verify the `volumes` output for the `app` and `worker` services. You should see maps resembling the following:

```yaml
    volumes:
      - type: bind
        source: /Users/username/reeldock/data
        target: /data
      - type: bind
        source: /Volumes/Synology/Media/Podcasts  # This should match your HOST_PODCASTS_DIR
        target: /media/podcasts
        bind:
          create_host_path: false
```

You can also validate the host podcast directory before starting the stack:

```bash
./scripts/check-docker-paths.sh
```

---

## 4. Startup Mount Failures

If `docker compose up` fails before the app or worker containers start, the problem is usually on the **host**, not inside the application.

### Common error: permission denied on `/host_mnt/Volumes/...`

```text
error while creating mount source path '/host_mnt/Volumes/Synology/Media/Podcasts':
mkdir /host_mnt/Volumes/Synology: permission denied
```

This means Docker cannot bind-mount `HOST_PODCASTS_DIR`. Typical causes:

1. The Synology (or other) share is **not mounted** in macOS — verify with:
   ```bash
   ls -la "/Volumes/Synology/Media/Podcasts"
   ```
2. **Docker Desktop File Sharing** does not include `/Volumes` — add it under Settings → Resources → File sharing, then restart Docker Desktop.
3. `HOST_PODCASTS_DIR` in `.env` points to a path that does not exist on the host.

The Compose file sets `create_host_path: false` on the podcast bind mount so Docker will **not** try to auto-create missing NAS paths. Create or mount the directory on the host first, then run:

```bash
./scripts/check-docker-paths.sh && docker compose up -d
```

### Container starts but exits immediately

If the mount succeeds but the container user cannot write to `/media/podcasts`, the entrypoint preflight check fails fast with a message about `OUTPUT_ROOT`. Check `PUID`/`PGID` in `.env` match the directory owner on the share. See [Paths and Volumes](paths-and-volumes.md).

### App crashes with `No 'script_location' key found in configuration`

The Docker image is missing Alembic migration files. Rebuild the image so `alembic.ini` and `alembic/` are included:

```bash
docker compose up --build -d
```

Verify after rebuild:

```bash
docker compose exec app ls /app/alembic.ini /app/alembic/versions/
```

### Preflight fails on first start, then succeeds on restart

Bind mounts (especially macOS `/Volumes/...` NAS paths) may not be ready the instant containers start. Before running Compose:

```bash
mkdir -p data config
./scripts/check-docker-paths.sh
docker compose up -d
```

Preflight retries up to 3 times (2 seconds apart) automatically. If all attempts fail, confirm `HOST_PODCASTS_DIR` exists on the host and `./data` is writable. Set `PUID`/`PGID` in `.env` to match your macOS user if needed.

---

## 5. Container Write Test

If you experience "Permission Denied" errors when running jobs, verify that the application has write access to your mounted host directory from inside the container:

```bash
# Test write access from the application container
docker compose exec app touch /media/podcasts/test_write.txt

# Verify the file was created on the host
ls -la /mnt/podcasts/test_write.txt  # Or your HOST_PODCASTS_DIR

# Clean up the test file
docker compose exec app rm /media/podcasts/test_write.txt
```

If this test fails, check the file permissions of the folder on your host machine and ensure the `PUID` and `PGID` environment variables in `.env` (or `docker-compose.yml`) match the host user that owns the share.

---

## 6. Health and Readiness Endpoints

The application exposes two probe endpoints:

| Endpoint | Purpose |
| :--- | :--- |
| `/health` | **Liveness** — returns `200` when the web process is running. Use for simple uptime monitoring. |
| `/ready` | **Readiness** — returns `200` when `OUTPUT_ROOT` and `WORK_DIR` are writable; returns `503` with per-path details otherwise. Used by the Docker healthcheck. |

```bash
# Liveness (always 200 if the app is up)
curl -fs http://localhost:8080/health

# Readiness (503 if output or work directories are not writable)
curl -fs http://localhost:8080/ready
```

If `/ready` starts failing **after** the containers were healthy, the NAS or bind mount likely dropped at runtime. Remount the share on the host, then restart the stack:

```bash
docker compose restart app worker
```
