# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in abs-media-importer, please report it responsibly:

1. Open a [private GitHub security advisory](https://github.com/andrewtryder/abs-media-importer/security/advisories/new) on this repository, or
2. Contact the repository owner through GitHub.

Do not disclose vulnerabilities publicly until a fix is coordinated.

## What to Include

- A clear description of the issue
- Steps to reproduce
- Affected version or commit
- Impact assessment, if known

## Do Not Include

- Secrets, API keys, or credentials
- Sensitive production data

## Security Practices

- Never commit secrets or `.env` files with real credentials
- Use `config.yml` and environment variables for deployment-specific settings
- Keep dependencies updated (Dependabot is enabled on this repository)

## Automated Scanning

This repository uses GitHub security workflows to catch issues early:

- **CodeQL** — GitHub default code scanning for Python, JavaScript, and Actions on push, pull request, and weekly schedule; configure under [Settings → Advanced Security](https://github.com/andrewtryder/abs-media-importer/settings/security_analysis), view alerts under [Security → Code scanning](https://github.com/andrewtryder/abs-media-importer/security/code-scanning)
- **Dependency Review** — blocks pull requests that introduce dependencies with known vulnerabilities at moderate severity or higher
- **OpenSSF Scorecard** — weekly analysis of open source security best practices, with results published to [scorecard.dev](https://scorecard.dev/viewer/?uri=github.com/andrewtryder/abs-media-importer)
- **Secret scanning** — TruffleHog runs on pull requests to detect verified secrets

## Deployment Hardening

For security, the application defaults to binding to `127.0.0.1` (localhost) inside `docker-compose.yml` to prevent unintended public exposure.

If you choose to expose the application to your Local Area Network (LAN) or public internet:
1. Enable Basic Authentication by setting `AUTH_ENABLED=true`, `AUTH_USERNAME`, and `AUTH_PASSWORD` in your environment.
2. Generate a secure, unique `APP_SECRET_KEY` using `openssl rand -hex 32` or python `import secrets; print(secrets.token_hex(32))`.
3. Use a reverse proxy (such as Caddy, Nginx, or Cloudflare Tunnels) with SSL/TLS if routing traffic over public networks.
