# Audiobookshelf Setup & Integration

`abs-media-importer` is designed to run alongside [Audiobookshelf](https://www.audiobookshelf.org/) (ABS). It writes files to a directory that ABS monitors and can automatically trigger an ABS library scan when a job completes.

## 1. Directory Alignment

Ensure your Audiobookshelf instance is pointed to the same physical storage folder that `abs-media-importer` writes to.

* **Docker setup**: If both ABS and `abs-media-importer` are run on the same Docker host, they should both mount the same host directory.
  * In `abs-media-importer` `.env`:
    `HOST_PODCASTS_DIR=/mnt/podcasts`
  * In your Audiobookshelf Docker Compose config:
    ```yaml
    volumes:
      - /mnt/podcasts:/podcasts
    ```
  * In this example, you would configure your Audiobookshelf Library to monitor `/podcasts`.

---

## 2. Directory Structure Expectations

Audiobookshelf scans files based on directory groupings. By default, it expects a structure of **`LibraryRoot/PodcastTitle/Episode.m4b`**.

`abs-media-importer` automatically handles this:
1. When submitting a video, you choose or create a destination folder (e.g. `TechTalk`).
2. The background worker downloads the video, converts it, and writes it to `/media/podcasts/TechTalk/Video Title.m4b`.
3. In Audiobookshelf, `TechTalk` will appear as a Podcast or Audiobook series, and `Video Title.m4b` will appear as an episode/track.

---

## 3. Automatic Library Scan API Integration

You can configure `abs-media-importer` to automatically tell Audiobookshelf to scan for new files as soon as a download finishes.

### Configuration

Add the following variables to your `.env` file:

```env
# Enable library scan after success
ABS_SCAN_AFTER_SUCCESS=true

# The URL of your Audiobookshelf server (accessible from the importer container)
# If on the same Docker network, you can use the service name:
ABS_BASE_URL=http://audiobookshelf:13378
# Otherwise, use the host IP or domain:
# ABS_BASE_URL=http://192.168.1.50:13378

# Audiobookshelf API Token
# Create this in ABS under Settings -> Users -> Root/Admin User -> API Tokens
ABS_API_TOKEN=your-long-api-token-string

# Audiobookshelf Library ID
# You can find this in ABS under Settings -> Libraries -> Click your Podcasts/Audiobooks library.
# The ID is visible in the URL of your browser (e.g., settings/libraries/bc7f781a-...)
ABS_LIBRARY_ID=bc7f781a-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```
