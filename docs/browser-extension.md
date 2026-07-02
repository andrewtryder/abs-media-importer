# Browser extension

An unpacked WebExtension (Manifest V3) that lets you queue the YouTube video open in
your browser into a local `abs-media-importer` instance. Supports Chrome and Firefox
development builds. Not published to any browser store.

For setup, build, and load instructions, see
[`browser-extension/README.md`](../browser-extension/README.md).

## Backend configuration

The extension talks to two endpoints that are gated behind a single feature flag:

| Method | Path                     | Auth            | Purpose                                  |
|--------|--------------------------|-----------------|------------------------------------------|
| GET    | `/api/extension/status`  | optional token  | Capability / health check                |
| POST   | `/api/extension/queue`   | optional token  | Queue a video; returns `job_id` + `job_url` |

Enable the API and (recommended) set a token in the backend `.env`:

```ini
EXTENSION_API_ENABLED=true
EXTENSION_API_TOKEN=          # openssl rand -hex 32
```

- With `EXTENSION_API_ENABLED=false` (default), both endpoints return `404`.
- With a token set, requests must include `Authorization: Bearer <token>` **or**
  `X-ABS-MEDIA-IMPORTER-Token: <token>`. Missing/wrong tokens return `401`.

See [configuration.md](configuration.md) for the full environment variable reference.

`POST /api/extension/queue` accepts an optional `allow_reimport` boolean for
intentional duplicate imports.

## Security notes

- Treat the extension API token like any other secret. The extension stores it in
  `chrome.storage.local` and sends it as a Bearer header; it is never committed.
- The backend re-validates the YouTube URL with `yt-dlp` server-side. The
  extension's client-side check is only for UX.
- The extension's host permissions include LAN ranges (`192.168.*`, `10.*`,
  `172.16.*`) so it can reach a backend on the same network. Trim these in
  `manifests/base.json` if you only ever talk to `localhost`.

## CI

`browser-extension/scripts/lint.mjs` validates that every manifest entry point
exists in `src/` and that the JavaScript parses. `scripts/build.mjs` produces
`dist/chrome/` and `dist/firefox/`. Neither step is currently wired into the
GitHub Actions workflow; run them manually from `browser-extension/`.
