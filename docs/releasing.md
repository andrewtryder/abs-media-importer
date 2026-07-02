# Releasing Guide

This repository uses [Release Please](https://github.com/googleapis/release-please) in manifest mode with two independently versioned components:

- Root app (`.`): backend/service release line
- Browser extension (`browser-extension`): extension release line

## Release Automation Overview

Release Please runs on pushes to `main` and manages:

- Release PRs
- Version bumps
- Git tags
- GitHub releases

The release configuration lives in:

- `release-please-config.json`
- `.release-please-manifest.json`
- `.github/workflows/release-please.yml`

## How version bumps happen

Do not manually edit versions for normal releases. Release Please updates versions from merged Conventional Commits.

### Backend-only changes

If commits change files outside `browser-extension/**`, Release Please bumps the root app component and updates:

- `pyproject.toml` (`project.version`)
- `app/main.py` (`FastAPI(... version=...)`)

### Extension-only changes

If commits only touch `browser-extension/**`, Release Please bumps only the extension component and updates:

- `browser-extension/package.json` (`version`)
- `browser-extension/manifests/base.json` (`version`)

The extension popup displays runtime manifest version from `chrome.runtime.getManifest().version`, so no manual UI version string updates are needed.

### Changes in both areas

If commits affect both root app files and extension files, each component can release independently in the same cycle.

## Auto-publish behavior for extension assets

When Release Please creates an extension release (`browser-extension--release_created == 'true'`), the workflow:

1. Installs extension dependencies
2. Builds Chrome and Firefox extension packages
3. Uploads ZIP artifacts to that extension GitHub release

If no extension release is created, packaging/upload steps are skipped.

## Commit conventions for predictable bumps

Use Conventional Commits so Release Please can determine semver bump type:

- `fix(...)`: patch
- `feat(...)`: minor
- `feat(... )!` or `BREAKING CHANGE:`: major

Suggested scopes:

- Backend/app: `api`, `worker`, `app`, `config`, etc.
- Extension: `browser-extension`

## Forcing a specific version

If you need to force a one-off version jump, use Release Please's `Release-As` footer in a commit message (for example: `Release-As: 2.0.0`), then remove/avoid it afterward.
