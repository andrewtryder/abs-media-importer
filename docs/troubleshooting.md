# Troubleshooting Guide

This guide covers common issues and questions when running `yt-abs-importer`.

## 1. yt-dlp Extractor Errors

### Video Unavailable
```
ERROR: [youtube] CcYToxtmFHs: Video unavailable
```
* **Cause**: The video is private, age-restricted, region-blocked, or has been taken down.
* **Solution**: Ensure the video is publicly accessible. The application cannot bypass age gates or private video restrictions.

### Unable to Extract Uploader ID
```
ERROR: Unable to extract uploader id
```
* **Cause**: YouTube frequently updates their site layout, which can break older versions of `yt-dlp`.
* **Solution**: Update `yt-dlp` to the latest version. In Docker, run:
  ```bash
  docker compose pull
  docker compose up --build -d
  ```

---

## 2. ffmpeg Fallback Errors

### Tag Text Incompatible
```
Tag text incompatible with output codec id 'mp4a'...
```
* **Cause**: This happens when the download contains metadata streams that are not supported by the `.m4b` container format.
* **Solution**: No action is needed. The background worker automatically detects this failure and retries extraction using an audio-only command (omitting video/album art streams) to ensure the file is successfully created.

---

## 3. Permission Denied on NFS/SMB Shares

### Symptoms
Jobs fail during the final phase with a log message indicating `Permission denied` when trying to write to `/media/podcasts/...`

### Fix
1. Find the UID/GID of the user that owns the mounted share on your host:
   ```bash
   ls -lan /mnt/podcasts
   ```
2. Note the numeric owner ID (e.g. `1001`) and group ID (e.g. `1001`).
3. Add or uncomment the `PUID` and `PGID` settings in your `.env` file to match these values:
   ```env
   PUID=1001
   PGID=1001
   ```
4. Restart the Docker stack:
   ```bash
   docker compose down
   docker compose up -d
   ```

---

## 4. Files Not Appearing in Audiobookshelf

If downloads complete successfully in `yt-abs-importer` but do not show up in Audiobookshelf:
1. Verify directory alignment (see [Audiobookshelf Guide](audiobookshelf.md)).
2. Make sure the files are inside a subfolder of your Audiobookshelf library directory (e.g. `/media/podcasts/ChannelName/Title.m4b`). ABS requires files to be at least one level deep to detect them.
3. Trigger a manual library scan in the Audiobookshelf UI (**Settings** -> **Libraries** -> **Scan**).
4. Configure [API Integration](audiobookshelf.md) to trigger scans automatically.

---

## 5. Archive File Skipping Downloads

### Symptoms
A job fails or finishes instantly with a message like:
```
[download] CcYToxtmFHs has already been recorded in the archive
```

### Cause
By default, `yt-dlp` logs completed video IDs to `/data/config/youtube-archive.txt` to prevent duplicate downloads.

### Fix
* **Option A: Enable Archive Bypass**: Set `ALLOW_ARCHIVE_BYPASS=true` in your `.env` file or dynamically on the Settings page.
* **Option B: Manually Edit the Archive**: Edit `/data/config/youtube-archive.txt` on your host machine and delete the line containing the corresponding YouTube ID.
  ```bash
  # Example to remove video ID CcYToxtmFHs
  grep -v "CcYToxtmFHs" data/config/youtube-archive.txt > /tmp/archive.tmp
  mv /tmp/archive.tmp data/config/youtube-archive.txt
  ```

---

## 6. Missing Chapters or Thumbnails

### Missing Chapters
* YouTube chapters are extracted directly from the video creator's timestamp list in the video description. If a video does not have timestamps defined in its description, no chapters can be embedded. This is normal behavior.

### Missing Thumbnail / Cover Art
* If embedding the cover art fails due to formatting issues, `ffmpeg` falls back to writing an audio-only file.
* You can manually embed a cover image into the `.m4b` file afterwards using `ffmpeg` from a terminal:
  ```bash
  ffmpeg -i "Input.m4b" -i cover.jpg -map 0:a -map 1 -c copy -disposition:v:0 attached_pic "Output.m4b"
  ```
