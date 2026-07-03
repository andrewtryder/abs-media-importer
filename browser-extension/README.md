# Browser extension for abs-media-importer

An unpacked WebExtension (Manifest V3) that lets you queue the YouTube video open in
your browser into a local `abs-media-importer` instance. Works with Chrome and Firefox
development builds. Nothing is published to a browser store.

## Features

- **Popup** on YouTube video pages with a one-click "Queue video" button.
- **Context menu** "Send to abs-media-importer" on YouTube pages and links.
- **Options page** to configure the server URL, API token, default destination
  folder, embed flags, the "trigger Audiobookshelf scan" toggle, and a default
  "allow re-import" toggle.
- **LAN support**: host permissions for `127.0.0.1`, `localhost`, and the
  `192.168.*` / `10.*` / `172.16.*` ranges are included so the extension can
  reach a backend on the same LAN.

## 1. Enable the extension API on the backend

Set these in the backend `.env` (see `.env.example`):

```ini
EXTENSION_API_ENABLED=true
EXTENSION_API_TOKEN=          # optional; generate with: openssl rand -hex 32
```

Then restart the backend. Verify with:

```bash
curl http://127.0.0.1:8080/api/extension/status
# {"ok": true, "app": "abs-media-importer", "auth_required": false, ...}
```

If a token is set, requests must include `Authorization: Bearer <token>` or
`X-ABS-MEDIA-IMPORTER-Token: <token>`. The extension sends the Bearer header.

## 2. Build and load the extension

Requires Node.js 18+.

```bash
cd browser-extension
npm run build        # builds both Chrome and Firefox into dist/
```

**Chrome**

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `browser-extension/dist/chrome/`

**Firefox**

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select `browser-extension/dist/firefox/manifest.json`

> Temporary add-ons in Firefox are removed on restart. For a persistent
> install, use `web-ext sign` with a Mozilla developer account.

## 3. Configure the extension

Click the extension icon → Options (or the gear icon on the popup) and set:

- **Server URL**: e.g. `http://192.168.1.50:8080` (no trailing slash)
- **API token**: the value of `EXTENSION_API_TOKEN` (leave blank if unset)
- **Default destination folder**: subfolder under `OUTPUT_ROOT` (optional)
- **Embed metadata / thumbnail / chapters**: passed through to the job
- **Trigger Audiobookshelf scan after success**: passed through to the job
- **Allow re-import by default**: sends `allow_reimport=true` for extension
  queue requests unless overridden in the popup

Use **Test connection** to verify the server is reachable and the token is
accepted.

## Endpoints used by the extension

| Method | Path                      | Purpose                                  |
|--------|---------------------------|------------------------------------------|
| GET    | `/api/extension/status`   | Health / capability check (options page) |
| POST   | `/api/extension/queue`    | Queue a video; returns `job_id` + `job_url` |

Both endpoints return `404` when `EXTENSION_API_ENABLED=false`, and `401` when
a token is configured but missing/wrong. See
[docs/configuration.md](configuration.md) for the full env var reference.

## Development

```bash
npm run lint          # syntax-check JS + verify manifest entry points exist
npm run build:chrome  # build only Chrome
npm run build:firefox # build only Firefox
```

Source layout:

```
browser-extension/
  icons/icon.svg
  manifests/{base,chrome,firefox}.json
  scripts/{build,lint}.mjs
  src/
    background.js        # service worker: context menu, queue calls, settings cache
    browser-api.js       # chrome.* / browser.* shim
    settings.js          # shared settings + YouTube URL validation
    popup.html / popup.js
    options.html / options.js
```

## Known limitations

- Only single YouTube video URLs are queued (`/watch?v=…`, `/shorts/…`, and
  `youtu.be/<id>`). Playlist and channel URLs are rejected by the backend unless
  `ALLOW_PLAYLISTS` / `ALLOW_CHANNELS` are enabled, and even then only the
  single resolved video is imported — full playlist/channel batch imports are
  not yet supported.
- Job progress is not surfaced in the extension; open the returned `job_url`
  in the web UI to track it.
- Notifications require the `notifications` permission, which is declared in
  the manifest.
