# Changelog

Changes to the analysis pipeline itself are versioned separately (`CURRENT_ANALYSIS_VERSION` in `backend/core/database.py`) and are visible in the web app under **Versions** or through `GET /changelog`.

## Unreleased

First public release under the Serendipid name.

### Added

- Configuration file for categories, languages, trusted authors and creators, excluded and sensitive Instagram folders, and the import priority folder, with export and import through the API (`/config`, `/config/export`, `/config/import`) and `scripts/config.py`.
- Password login for the web app, with signed session cookies that expire after three weeks.
- Media and thumbnails are served through the web app, so browsers never contact the backend.

### Changed

- Renamed the project from SuperBrain to Serendipid: folders, environment variables (`SERENDIPID_*`), the database file (`serendipid.db`) and the Docker service.
- Access tokens are 32 characters, accepted only in the `X-API-Key` header, and no longer written to the log. Existing 8-character tokens are replaced on the next start.
- `/media` and `/static` require the access token.
- `/connect-info` only answers direct requests from the local network.
- Docker: one port (5050), one worker, persistent volumes for the database, media and token, and every provider key passed through.
- `deploy.sh` works with any checkout location and service name.
- One-off data migrations moved to `backend/scripts/migrations/`.

### Removed

- The `superbrain-server` npm package and its CLI.
- Android app leftovers and the GitHub workflows that built the APK and published packages.
- Runtime state files that had been committed (`model_rankings.json`, `openrouter_free_models.json`, `ngrok_enabled.txt`, `whisper_model.txt`).

## Before Serendipid

Serendipid began as a fork of [SuperBrain](https://github.com/sidinsearch/superbrain). Development since August 2026 added the web app, the iOS app, semantic search and chat, study guides, boards, importance and eloquence scoring, the Instagram export importer, batch mode and the rescan pipeline.
