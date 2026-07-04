# Browser extension

An unpacked WebExtension (Manifest V3) that lets you queue the YouTube video open in
your browser into a local `reeldock` instance. Supports Chrome and Firefox
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
  `X-REELDOCK-Token: <token>`. Missing/wrong tokens return `401`.

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

The `browser-extension` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
runs on every push and pull request to `main`:

```bash
npm ci --prefix browser-extension
npm --prefix browser-extension run lint
npm --prefix browser-extension run check:version
npm --prefix browser-extension run build
npm --prefix browser-extension run package
```

`lint` validates manifest entry points and JavaScript syntax. `check:version`
ensures `package.json`, `manifests/base.json`, and `.release-please-manifest.json`
agree on the extension version. `build` and `package` produce `dist/` and ZIP
artifacts under `browser-extension/artifacts/`.
