# Contributing

Thank you for your interest in contributing to this project! We welcome contributions from everyone.

## How to contribute

1. **Fork the repository** (if you're an external contributor) or create a feature branch.
2. **Install [uv](https://docs.astral.sh/uv/getting-started/installation/)** and set up the development environment:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip sync requirements-dev.lock
   ```
3. **Follow the Conventional Commits** standard for commit messages (`feat:`, `fix:`, `chore:`, `docs:`, etc.).
4. **Run quality checks locally** before submitting a pull request:
   - Format check
   - Lint
   - Typecheck (if applicable)
   - Tests
   - Build (if applicable)
5. **Open a pull request** with a clear title and description of your changes.

When changing dependencies, edit `requirements.txt` and/or `requirements-dev.txt`, run `./scripts/compile-requirements.sh`, sync with `uv pip sync requirements-dev.lock`, and commit the updated lock files.

## Pull request guidelines

- Keep PRs focused on a single concern. If you have multiple unrelated changes, split them into separate PRs.
- Update documentation (README, ADRs) if your change introduces new behavior or deprecates existing functionality.
- If your change affects repository governance or CI/CD, add a note in the PR description.

## Code of Conduct

We expect all contributors to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a respectful and welcoming environment for everyone.

## Questions?

Open a discussion or issue. We're happy to help.
