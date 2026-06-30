# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in yt-abs-importer, please report it responsibly:

1. Open a [private GitHub security advisory](https://github.com/andrewtryder/yt-abs-importer/security/advisories/new) on this repository, or
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
