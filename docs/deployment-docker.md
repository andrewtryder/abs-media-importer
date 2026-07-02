# Docker Deployment Guide

This guide details how to deploy `abs-media-importer` using Docker Compose, verify your configuration, and troubleshoot volume access issues.

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
        source: /Users/username/abs-media-importer/data
        target: /data
      - type: bind
        source: /Volumes/Synology/Media/Podcasts  # This should match your HOST_PODCASTS_DIR
        target: /media/podcasts
```

---

## 4. Container Write Test

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
