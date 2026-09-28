---
name: ha-addon-development
description: "Guidelines and architecture for developing the Home Assistant Add-on 'ha-streaming-hub'."
---
# Home Assistant Add-on Development

This skill provides context for the `ha-streaming-hub` project.

## Architecture
- **Type**: This is a Home Assistant Add-on (runs as a Docker container managed by Supervisor), NOT a HACS Integration (`custom_components`).
- **Configuration**: The add-on metadata is strictly managed in `streaming_hub/config.yaml` and `streaming_hub/build.yaml`.
- **Backend**: Python-based API and logic located in `streaming_hub/backend/`. Uses `ruff` for linting.
- **Frontend**: Web interface located in `streaming_hub/frontend/`.
- **Rootfs**: Used for overriding or placing specific overlay files in the Docker container (`streaming_hub/rootfs/`).
- **Dockerfile**: The main entrypoint that builds the image, located at `streaming_hub/Dockerfile`.

## Workflows
1. **Linting**:
   - Python code must pass `uvx ruff check .` and `uvx ruff format --check .`.
   - Use `pre-commit run --all-files` locally to check for issues.
2. **Releases**:
   - The version bump is handled automatically by `release-please` via GitHub Actions.
   - Do NOT manually bump versions in `config.yaml` unless fixing a broken release. 
   - Commit messages must follow Conventional Commits (e.g., `feat: ...`, `fix: ...`, `chore: ...`).

## Rules
- Avoid boilerplate: don't overengineer the scripts.
- Use native HA add-on features where possible (e.g. relying on `bashio` for shell scripts if used, using `S6-overlay` for services).
- Strictly adhere to `GEMINI.md` for language and commit policies.
