# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FastAPI backend for SuperBrain — analyzes saved Instagram posts, YouTube videos, and web pages with AI (summary, category, tags, transcription, music ID) and serves them to the mobile app, web viewer, and dashboard over a token-authenticated REST API. Data lives in a local SQLite database; there is no cloud component.

## Commands

### Run locally (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python start.py        # first-run setup wizard (API keys, Instagram login, venv) + launches uvicorn --reload
python api.py           # run the API directly, skipping the wizard (uvicorn on :5000, no reload)
python start.py --reset # re-run the setup wizard
```

### Run with Docker

```bash
cp .env.example .env    # fill in at least one AI provider key
./start-docker.sh        # dev: docker compose build && up -d
./start-docker-prod.sh   # prod: --no-cache build, waits on /health
docker compose logs -f superbrain-api
curl http://localhost:5000/health
```

### Tests

There is no `pytest` in `requirements.txt` — install it separately. Only `tests/test_access_token.py` is a real pytest suite (`fastapi.testclient.TestClient` against the live `app`); `tests/test_api.py`, `tests/test_db.py`, and the root-level `test_backend.py` are manual scripts that expect a server/DB already running and are invoked directly with `python`, not `pytest`.

```bash
pytest tests/ -v                                          # discovers only test_access_token.py meaningfully
pytest tests/test_access_token.py -v                       # single file
pytest tests/test_access_token.py::test_ping_works_without_auth -v  # single test
python test_backend.py                                     # manual smoke test, needs server running on :5000
```

### Utility CLIs

```bash
python core/model_router.py            # show current AI provider rankings
python core/model_router.py reset <key>
python core/model_router.py refresh    # force-refresh the OpenRouter free-model list
python utils/db_stats.py               # database statistics
python utils/manage_token.py           # view/reset the API access token
python scripts/backfill_embeddings.py  # generate embeddings for posts saved before that feature existed
python scripts/score_importance.py     # score importance (1-5) for posts saved before that feature existed
python instagram/instagram_login.py    # interactive Instagram login (handles 2FA), caches session
```

## Architecture

### `api.py` and `main.py` are decoupled by subprocess — this is the key thing to understand

`api.py` is the FastAPI app (routes, queue, auth). `main.py` is a separate CLI script (`python main.py <url>`) that runs the actual analysis pipeline for one Instagram URL (download → visual/audio/text/music analyzers → AI summary/embedding → save). **`api.py` does not import `main.py`** — for every `/analyze` request it spawns `main.py` as a subprocess (`api.py:561`) from a thread pool and parses its stdout/stderr for success/quota-error signals. This is deliberate: a crash or hang in one analysis can't take down the API process. Keep this in mind when tracing an analysis end-to-end — you have to follow the subprocess boundary, not a function call.

YouTube and webpage analysis, by contrast, run in-process via `analyzers/youtube_analyzer.py` / `analyzers/webpage_analyzer.py` — only Instagram posts go through the `main.py` subprocess pipeline, because they have multiple media components (visual + audio + music + caption) orchestrated together.

### `analyzers/`

One module per analysis concern, each exposing `analyze_<x>(url) -> dict` returning content fields plus `error: str | None` and platform metadata (thumbnail, author, date):
- `youtube_analyzer.py` — Gemini native YouTube URL understanding (no download), with model fallback on 429
- `webpage_analyzer.py` — multi-strategy scrape (trafilatura/newspaper4k) + AI summary
- `visual_analyze.py`, `audio_transcribe.py`, `music_identifier.py`, `text_analyzer.py`, `caption.py` — granular Instagram-post components, orchestrated together by `main.py`

### `core/`

- **`database.py`** — SQLite (stdlib `sqlite3`, no ORM), WAL mode, `DATABASE_PATH` env var (defaults to `backend/superbrain.db`). Tables: `analyses` (main content), `processing_queue`, `collections` (seeded with a default "Watch Later"), `deleted_log` (soft-delete sync for mobile), `analysis_changelog`. Singleton: `get_db()`.
  - **No migration framework.** Schema changes are added as `ALTER TABLE ... ADD COLUMN` wrapped in `try/except sqlite3.OperationalError: pass` in `_create_tables()` — idempotent, runs on every startup. Follow this exact pattern for new columns; don't introduce Alembic or a separate migration step.
  - `CURRENT_ANALYSIS_VERSION` (currently `7`) is stamped on every saved post; posts saved under an older pipeline version get flagged for review. Its history is queryable over the API via `GET /changelog` (backed by the `analysis_changelog` table, seeded in `_seed_changelog()`). **This changelog exists and should be kept current: whenever the reel/Instagram analysis process changes, add a matching entry to both `_seed_changelog()` and the version-history comment block directly above the constant. Only bump `CURRENT_ANALYSIS_VERSION` itself when the change is significant enough to be worth flagging previously-saved posts for review** — not every change to the pipeline warrants that (use judgment, or ask).
- **`model_router.py`** — the AI Model Router (below).
- **`link_checker.py`** — detects whether a URL is Instagram/YouTube/webpage.
- **`media_store.py`** — relocates downloaded media from `temp/` to permanent `media/<shortcode>/`.
- **`categories.py`, `category_manager.py`, `languages.py`** — taxonomy normalization and language-detection prompts used across analyzers.
- **`importance.py`** — importance-scoring prompt/parser (see "Importance scoring" below).

### AI Model Router (`core/model_router.py`)

Multi-provider fallback so free-tier rate limits/downtime never block an analysis: **Groq → Gemini → OpenRouter (hardcoded best free models) → dynamically-discovered OpenRouter free models → local Ollama** (OpenAI GPT-4.1 tried first if `OPENAI_API_KEY` is set). Vision tasks have their own priority order.

- Ranking = `base_priority` + a latency penalty from an EMA of past response times — faster models get promoted.
- On failure, a model gets a cooldown (30 min for HTTP 429, shorter otherwise) before the router retries it.
- A background thread refreshes the OpenRouter free-model list every 6 hours and scores new candidates by context length, capabilities, recency, provider trust.
- State persists across restarts in `config/model_rankings.json`; the free-model cache persists in `config/openrouter_free_models.json`.

When adding a new AI-backed feature, route model calls through this singleton (`get_router()`) rather than calling a provider SDK directly — that's what gives every analysis type automatic fallback.

### Config — two layers that don't fully overlap

`config_settings.py` (a `Settings`/`DevelopmentSettings`/`ProductionSettings` hierarchy reading env vars) looks like the intended single source of config truth, but **`api.py` and `model_router.py` don't import it** — they read `os.getenv(...)` and `config/.api_keys` directly. Don't assume changing `config_settings.py` affects runtime behavior; check where the value is actually consumed.

- `config/.api_keys` (gitignored) — actual secrets: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `INSTAGRAM_USERNAME`, `INSTAGRAM_PASSWORD`. Template: `config/.api_keys.example`.
- `.env` (gitignored, Docker-oriented) — template: `.env.example`.
- `token.txt` (gitignored, auto-generated on first run) — the API access token; required as `X-API-Key` header (or `?token=` query param) on most endpoints (`verify_token`, `api.py`).
- `config/model_rankings.json`, `config/openrouter_free_models.json` — router state, not secrets, but generated/mutated at runtime.

### API route groups (`api.py`, all routes defined directly, no sub-routers)

- Ingestion: `POST /analyze`, `GET /caption`, `GET /cache/{shortcode}`, `GET /analysis-status/{shortcode}`
- Browse/search: `GET /recent`, `GET /search`, `GET /search/semantic`, `GET /categories`, `GET /category/{category}`, `GET /stats`, `GET /changelog`
- Sync (mobile client): `GET /sync`, `GET /sync/deleted`
- Post management: `PUT /post/{shortcode}`, `DELETE /post/{shortcode}`
- Collections: `GET/POST /collections`, `PUT /collections/{id}/posts`, `DELETE /collections/{id}`
- Queue: `GET /queue-status`, `GET /queue/retry`, `POST /queue/retry/flush`, `DELETE /queue/{shortcode}`
- Import/export: `GET /export`, `POST /import`, `POST /import/file`
- Settings: `GET/POST/DELETE /settings/ai-providers`, `GET/POST/DELETE /settings/instagram`
- Ops: `GET /ping`, `GET /status`, `GET /health`

Note: there are **no server-side notification endpoints** — "Watch Later" reminders are scheduled entirely client-side in the mobile app (Expo/Android notification channels), not by this backend.

Interactive docs: `http://localhost:5000/docs` (Swagger) and `/redoc`.

## Git commits

- Do not add Claude, or any `Co-Authored-By: Claude` / Claude Code attribution trailer, to commit messages in this repo.
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, etc.) for commit message subject lines, matching existing history.

## Importance scoring

Every post gets a 1-5 `importance` score (`analyses.importance`, nullable) rating how much lasting/reusable value it has, so posts can be sorted by "worth revisiting" instead of only by recency (`GET /recent?sort=importance`, see `core/database.py:get_recent_light`). This exists specifically so low-value content (memes, pure personal-branding clips) doesn't crowd out genuinely useful content (a taught technique, a well-developed idea) in review.

- **`core/importance.py`** — `IMPORTANCE_PROMPT` (spliced into `main.py`'s structured summary prompt as the `⭐ IMPORTANCE` field, alongside `📂 CATEGORY`/`🌐 LANGUAGE`) and `parse_importance()`. The rubric is deliberately **topic- and format-agnostic** — it scores on depth of payload (a fully-explained technique, or a genuinely developed idea/argument — practical and conceptual value are weighted equally, so philosophy/book content that "sparks thought" scores as well as a concrete how-to) rather than on subject matter or whether the post is formatted as a meme/joke. A meme can score high if a real insight can reasonably be extrapolated from its premise even when unstated; a "serious"-sounding post scores low if it only shows off or namedrops without explaining anything. Calibrated against real saved posts (not written in the abstract) — see the comment above `IMPORTANCE_PROMPT` for the specific before/after example that shaped the wording.
- **`TRUSTED_CREATORS`** (also in `core/importance.py`) — a small, explicit, code-level allowlist of usernames whose posts the user has manually confirmed are consistently worth revisiting, independent of any single post's per-post score (the LLM scores each post in isolation with no memory of other posts by the same creator, so this is a deliberate override, not something asked of the model). `apply_trusted_creator_boost()` floors — never lowers — a trusted creator's score at 4. Seeded with `erinmerylstudy`. Applied in `main.py` right after `username`/`channel`/`author` is resolved for each of the three pipelines (Instagram, YouTube, webpage), and again in the backfill script from the post's already-stored `username`.
- Existing posts (saved before this feature) have `importance IS NULL`, not `0` — "unscored" is kept distinguishable from "scored low." Run `python scripts/score_importance.py` to backfill them: it scores from each post's already-stored title/summary/tags/category (no re-download, no full re-analysis) and stamps the post to `CURRENT_ANALYSIS_VERSION` on success, which is what clears it from the version-6 review-queue flag.
- This is `CURRENT_ANALYSIS_VERSION` bump **6** — see the version-history comment above the constant and the matching `_seed_changelog()` entry in `core/database.py` for the full description.
