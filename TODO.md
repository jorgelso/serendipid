# TODO

Known gaps and planned work, roughly in priority order within each section.

## Configuration in the web app

The backend supports a configuration file with export and import (see [docs/CONFIGURATION.md](docs/CONFIGURATION.md)), but the web app has no UI for it yet.

- [ ] Settings page that shows the current configuration (`GET /config`).
- [ ] Edit categories (names and fallback keywords), languages, trusted authors, trusted creators, excluded folders, sensitive folders and the priority folder, saving through `POST /config/import`.
- [ ] Create a configuration from the defaults (`GET /config/default`) as a starting point.
- [ ] Import a configuration file and download the current one (`GET /config/export`).
- [ ] After a category or language change, offer to re-analyze affected posts so existing posts pick up the new labels.

## Reduce the OpenAI requirement

These features call OpenAI directly with no fallback, so they fail without `OPENAI_API_KEY`:

- [ ] Study guides (`STUDY_GUIDE_MODEL` in `backend/core/study_guide.py`).
- [ ] Importance scoring (`IMPORTANCE_MODEL` in `backend/core/model_router.py`).
- [ ] Embeddings, which semantic search, related posts, chat retrieval and the 3D map depend on (`text-embedding-3-small`). A local embedding model (for example through Ollama) would remove the dependency.
- [ ] Eloquence scoring (pinned to `gpt-4.1` in `backend/core/eloquence.py`).
- [ ] Make the pinned model names configurable instead of constants.
- [ ] `ANALYSIS_MODE=batch` is OpenAI-only by design; document it as such or support Anthropic's batch API.

## iOS app

The iOS app has not kept up with the backend.

- [ ] Accept the 32-character mixed-case access token. Token entry is still an 8-box field that uppercases input (`TokenEntryField.swift`, `AccessToken` in `ServerConfigStore.swift`).
- [ ] Send `X-API-Key` when loading media and thumbnails. `/media` and `/static` now require it, and the app currently loads them as plain URLs (`MediaResolver.swift`).
- [ ] Bring models and screens up to date with the backend's current responses and features (boards, study guides, eloquence, versions).
- [ ] The app group and bundle identifiers changed with the rename (`com.serendipid.ios`, `group.com.serendipid.ios.shared`); existing installs see an empty pending-share queue.
- [ ] Verify the share extension end to end against the current `/analyze` responses.

## Backend

- [ ] Include boards in `GET /export`, `POST /import` and `POST /reset/database`.
- [ ] Remove `core/category_manager.py`, which still targets the old MongoDB storage and no longer works.
- [ ] `config_settings.py` is not used by `api.py` or the model router; either wire it in or remove it.
- [ ] Make the server port (`API_SELF_PORT`, 5050) configurable.
- [ ] Rate-limit failed access-token attempts.
- [ ] Turn the manual scripts in `backend/tests/` and `backend/test_backend.py` into a real pytest suite and add `pytest` to a dev requirements file.
- [ ] The Docker image has no local Whisper; consider an optional image variant with it.

## Web app

- [ ] Feature flag for eloquence scoring, so the Eloquent page and Admin card can be hidden for people who don't use it.
- [ ] Ideas v2: group recurring topics by meaning rather than exact tag text (AI-extracted claims, embedded and clustered), and use the same claims to improve study guide synthesis. See `serendipid-web/src/lib/ideas.ts` and `backend/core/study_guide.py`.
- [ ] The minimum importance for ideas and study guides is duplicated in `serendipid-web/src/lib/ideas.ts` and `backend/core/study_guide.py`; serve it from the backend instead.
- [ ] Rate-limit or lock out repeated failed sign-ins (currently only a fixed delay).
- [ ] Add tests; `npm run lint` is the only automated check.

## Project

- [ ] Build the iOS app in CI (needs a macOS runner).
- [ ] Multi-user support is out of scope for now; the app assumes one owner per backend.
