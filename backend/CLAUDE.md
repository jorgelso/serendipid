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

- **`database.py`** — SQLite (stdlib `sqlite3`, no ORM), WAL mode, `DATABASE_PATH` env var (defaults to `backend/superbrain.db`). Tables: `analyses` (main content), `processing_queue`, `batch_jobs` (ANALYSIS_MODE=batch resume state, see "Batch mode" below), `collections` (seeded with a default "Watch Later"), `deleted_log` (soft-delete sync for mobile), `analysis_changelog`. Singleton: `get_db()`.
  - **No migration framework.** Schema changes are added as `ALTER TABLE ... ADD COLUMN` wrapped in `try/except sqlite3.OperationalError: pass` in `_create_tables()` — idempotent, runs on every startup. Follow this exact pattern for new columns; don't introduce Alembic or a separate migration step.
  - `CURRENT_ANALYSIS_VERSION` (currently `8`) is stamped on every saved post; posts saved under an older pipeline version get flagged for review. Its history is queryable over the API via `GET /changelog` (backed by the `analysis_changelog` table, seeded in `_seed_changelog()`). **This changelog exists and should be kept current: whenever the reel/Instagram analysis process changes, add a matching entry to both `_seed_changelog()` and the version-history comment block directly above the constant. Only bump `CURRENT_ANALYSIS_VERSION` itself when the change is significant enough to be worth flagging previously-saved posts for review** — not every change to the pipeline warrants that (use judgment, or ask).
- **`model_router.py`** — the AI Model Router (below).
- **`link_checker.py`** — detects whether a URL is Instagram/YouTube/webpage.
- **`media_store.py`** — relocates downloaded media from `temp/` to permanent `media/<shortcode>/`.
- **`categories.py`, `category_manager.py`, `languages.py`** — taxonomy normalization and language-detection prompts used across analyzers.
- **`importance.py`** — importance-scoring prompt/parser (see "Importance scoring" below).
- **`summary_parser.py`** — pure parsing of the combined title/summary/tags/music/category/language AI output (`parse_summary()`, moved out of `main.py` so `batch_processor.py` can reuse it without importing `main.py`).
- **`batch_processor.py`** — resumption logic for `ANALYSIS_MODE=batch` (see "Batch mode" below). First-analysis-only — the rescan pipeline (below) deliberately does not use or extend this module.
- **`rescan_plan.py`, `rescan_dates.py`, `rescan_batch_processor.py`** — the rescan pipeline (see "Rescan pipeline" below).

### AI Model Router (`core/model_router.py`)

Multi-provider fallback so free-tier rate limits/downtime never block an analysis: **Groq → Gemini → OpenRouter (hardcoded best free models) → dynamically-discovered OpenRouter free models → local Ollama** (OpenAI tried first if `OPENAI_API_KEY` is set, using whichever model `OPENAI_TEXT_MODEL` resolves to — see below). Vision tasks have their own priority order.

`OPENAI_TEXT_MODEL` (env var, default `gpt-4.1`) is the single knob for which OpenAI chat model the router's "openai" provider slot uses — it's read once into the `OPENAI_TEXT_MODEL` constant at the top of `model_router.py` and referenced everywhere an OpenAI model id is needed: the text/vision/chat entries in `MODELS`, `generate_importance_text()`'s pin (see below), and `build_batch_chat_request()`'s default. Both `gpt-4.1` and `gpt-5.6-luna` are known-good here — `_openai_chat_params()` builds the request body's token-limit/temperature fields differently depending on which one is active, since the GPT-5.x family rejects the legacy `max_tokens` param (needs `max_completion_tokens`) and rejects any non-default `temperature`. Set `OPENAI_TEXT_MODEL=gpt-5.6-luna` to switch every OpenAI call over at once; unset (or `gpt-4.1`) to stay on the default.

- Ranking = `base_priority` + a latency penalty from an EMA of past response times — faster models get promoted.
- On failure, a model gets a cooldown (30 min for HTTP 429, shorter otherwise) before the router retries it.
- A background thread refreshes the OpenRouter free-model list every 6 hours and scores new candidates by context length, capabilities, recency, provider trust.
- State persists across restarts in `config/model_rankings.json`; the free-model cache persists in `config/openrouter_free_models.json`.
- `generate_importance_text()` is a deliberate exception to the latency-ranked routing above — it pins to `OPENAI_TEXT_MODEL` specifically (falling back to the normal ranked order only if OpenAI is unavailable/fails), because importance scoring needs consistent judgment across posts more than it needs speed. See "Importance scoring" below.

When adding a new AI-backed feature, route model calls through this singleton (`get_router()`) rather than calling a provider SDK directly — that's what gives every analysis type automatic fallback.

### Batch mode (`ANALYSIS_MODE=batch`)

An alternative to the default synchronous pipeline for the Instagram reel path only (YouTube/webpage analysis are single-call pipelines and always stay synchronous). Set the `ANALYSIS_MODE` env var to `batch` (default `immediate`) to submit visual analysis, text analysis, the combined-summary call, importance scoring, and embedding — every OpenAI call in the pipeline — to **OpenAI's Batch API** instead of calling them synchronously: roughly half the per-call cost, in exchange for turnaround of minutes up to 24h per phase. Batch mode is OpenAI-only by construction (no other configured provider has an equivalent async batch endpoint), so it only makes sense if OpenAI is actually the provider you'd otherwise be paying for these calls — check `config/model_rankings.json`'s per-provider success/fail counts before assuming that's true; if Groq/Gemini/OpenRouter are actually answering most calls (their free tiers), there's nothing to batch-save on those, and fixing whatever's making them fail (e.g. a missing SDK package) saves far more than batching ever could. Audio transcription (Groq/local Whisper) and music ID (Shazam) never touch OpenAI, so they always stay synchronous regardless of `ANALYSIS_MODE` — nothing to batch there.

- `main.py` reads `ANALYSIS_MODE` itself (it's a separate subprocess). In batch mode it still runs audio transcription and music ID synchronously as normal (Phases 2-3, unaffected), but visual analysis (Phase 1) and text analysis (part of Phase 3) are skipped synchronously — instead, once audio/music are done, it builds one vision request per video/image file (reusing `analyzers/visual_analyze.py`'s own frame-extraction/`VISION_PROMPT`) plus one text-analysis request (reusing `analyzers/text_analyzer.py`'s `build_text_analysis_prompt()`), bundles all of them into a single OpenAI Batch API job (all `/v1/chat/completions`, since a batch job is single-endpoint), persists everything needed to resume later into the `batch_jobs` table (`core/database.py`), and exits with code `3` — a new exit code distinct from `0`=success/`1`=failure/`2`=queued-for-retry, so `api.py` knows not to treat it as a failure and not to remove the `processing_queue` row (already set to `status='batch'`).
- Because `main.py`'s subprocess exits right after submitting, there's no live process to resume in when a batch completes — that's what `core/batch_processor.py`'s `check_and_advance_batches()` is for, called **in-process** by `api.py`: once on backend startup, and on demand via `POST /batches/check` (the "Check batches" button in `superbrain-web`'s nav bar). Deliberately **no periodic polling** — this app runs on a machine that isn't always on, so batch-pending items just wait until the next startup or manual check.
- Three phases per shortcode, tracked in `batch_jobs.phase`: `analysis_pending` (the bundled vision+text batch, the normal entry point) → `summary_pending` (once that resolves, the parsed visual/text output feeds the combined-summary prompt, submitted as its own batch) → `scoring_pending` (summary resolved; importance-scoring and embedding batches submitted concurrently as two separate sub-batches, since an OpenAI batch job is single-endpoint — one `/v1/chat/completions` job, one `/v1/embeddings` job). Once both sub-batches are terminal, `db.save_analysis()` is called — same call the immediate pipeline uses — and the `batch_jobs` row is deleted. A reel with no video/image files and no `info.txt` (rare) skips straight to `summary_pending` instead, since there's nothing to submit for the analysis phase.
- A failed/expired/cancelled **analysis** or **summary** batch re-queues the item via the existing `db.queue_for_retry()` mechanism (reuses the retry-drain machinery `queue_worker()` already has for quota errors) — a full retry re-downloads and redoes everything from scratch. A failed importance or embedding sub-batch degrades gracefully to `None` instead — matching the immediate pipeline's existing best-effort treatment of those two fields.
- Batch-produced posts are stamped `model_used="openai_gpt41_batch"` (vs. the immediate pipeline's `"openai_gpt41"` or whichever provider actually answered) for visibility into which posts went through which path.
- Extending visual/text analysis to batch mode meant the pure prompt-building/output-cleaning helpers (`build_final_summary_prompt()`, `_clean_visual()`/`_clean_audio()`/`_clean_text()`/`_extract_section()`) had to move out of `main.py` into `core/summary_parser.py` too, alongside `parse_summary()`/`apply_music_override()` — `core/batch_processor.py`'s analysis-phase resumption needs them to reconstruct a `results` dict and build the summary prompt without importing `main.py`. `main.py` imports them back from there; behavior for the immediate pipeline is unchanged.

### Rescan pipeline (`scripts/rescan_post.py`, `core/rescan_plan.py`, `core/rescan_dates.py`, `core/rescan_batch_processor.py`)

Fixes a post whose analysis is stale relative to `CURRENT_ANALYSIS_VERSION` (or whose underlying analyzer prompt changed since it was last analyzed) without redoing more work than necessary. **Deliberately a fully separate pipeline from first-time analysis** — `main.py` and `core/batch_processor.py` are never imported from or modified by it, and it never calls `db.hard_delete_post()`; every write goes through `db.save_analysis()`'s existing upsert (`INSERT ... ON CONFLICT(shortcode) DO UPDATE`), so a rescan that fails partway (a redownload that turns out to be impossible, an expired OpenAI batch request) always leaves the original row exactly as it was, never half-deleted or blanked.

- **The four Instagram analyzer scripts have no Instagram/network dependency** — `analyzers/visual_analyze.py`, `audio_transcribe.py`, `music_identifier.py`, `text_analyzer.py` each just take a local file path as their only CLI argument. `main.py` happens to invoke them against files fresh out of `temp/` during first analysis, but they work identically against files already sitting in `media/<shortcode>/` (permanent storage since `CURRENT_ANALYSIS_VERSION` 3) — which is the fact this whole pipeline is built on: a rescan re-runs these scripts directly against already-downloaded media, and only triggers a real Instagram re-download when a post's local media is genuinely missing (rare — nearly every post in a real library already has `media_files` populated).
- **Version-gap-aware, not a blanket re-run.** `core/rescan_plan.py`'s `decide_rescan_plan(row)` compares a post's `analyzed_at` against dated cutoffs in `core/rescan_dates.py` — one per known analyzer-prompt change (e.g. the 2026-08-08 vision-prompt rewrite, the 2026-08-09 frame-sampling fix, the 2026-08-10 audio-failure-silencing fix) — and only re-runs the specific analyzer(s) that actually changed since that post was last analyzed. `analyzers/text_analyzer.py` and `music_identifier.py` haven't changed, so their stored output is always reused as-is. Category/language/importance/caption-mismatch gaps don't need their own flags — they're all downstream of the combined-summary LLM call, which every non-cheap rescan rebuilds regardless of which analyzer steps were skipped. Add a new cutoff to `rescan_dates.py` whenever an analyzer prompt changes again, so future rescans know to redo just that step for posts analyzed before it.
- **Correctness trap to know about**: `save_analysis()` only protects `embedding`/`media_files`/`importance`/`caption` from being blanked by an empty value (`CASE WHEN excluded.X != '' THEN excluded.X ELSE analyses.X END`) — every other column, including `visual_analysis`/`audio_transcription`/`text_analysis`, is unconditionally overwritten with whatever is passed. Any rescan step that gets skipped **must** pass the existing stored value for that column through explicitly, never `""`.
- **Two invocation modes, one script**: `python scripts/rescan_post.py <shortcode>` rescans a single post synchronously (immediate LLM calls, regardless of `ANALYSIS_MODE`) — the individual "Re-run analysis" UI action always gets an instant result. `python scripts/rescan_post.py --batch <sc1,sc2,...>` rescans a whole cohort (e.g. "rescan this entire version"): under `ANALYSIS_MODE=immediate` (default) it loops through the list synchronously in one background process; under `ANALYSIS_MODE=batch` it submits every targeted post's summary prompt together as **one shared OpenAI Batch API job** (`router.submit_openai_batch()` called once with the whole cohort's requests) rather than one job per post — unlike first-analysis's batch mode, which only ever processes one reel at a time and so only ever submits size-1 batches.
- **`rescan_batch_jobs`** is a separate table from `batch_jobs`, same two-phase shape (`summary_pending` → `scoring_pending`), advanced by `core/rescan_batch_processor.py`'s own `check_and_advance_rescan_batches()` (its own lock, its own terminal-state handling — not a call into `batch_processor.py`). It exists as its own table specifically because many shortcodes can share one `summary_batch_id` here, which `batch_jobs`'s existing callers aren't shaped for. On a failed/expired batch request (including OpenAI's `batch_expired` error for a request that didn't complete within the batch's completion window), the rescan pipeline just deletes that shortcode's `rescan_batch_jobs` row and leaves its `analyses` row untouched — it stays at its old version and simply gets picked up again on the next rescan, unlike a failed first-analysis batch (`batch_processor.py`), which re-queues a real retry because there's no prior saved row to fall back to there.
- Advancement happens the same way as first-analysis batch mode: once on backend startup, and on demand via `POST /rescan/batches/check` — no periodic polling.

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
- Queue: `GET /queue-status`, `GET /queue/retry`, `POST /queue/retry/flush`, `DELETE /queue/{shortcode}`, `POST /batches/check` (manual check for `ANALYSIS_MODE=batch` completions — see "Batch mode" above)
- Rescan: `POST /reanalyze/bulk` (single or many shortcodes — see "Rescan pipeline" above), `POST /rescan/batches/check` (manual check for rescan `ANALYSIS_MODE=batch` completions, distinct from `POST /batches/check`)
- Import/export: `GET /export`, `POST /import`, `POST /import/file`
- Instagram export import (distinct from the above — see "Instagram export import" below): `POST /instagram-export/preview`, `POST /instagram-export/jobs`, `GET /instagram-export/jobs`, `GET /instagram-export/jobs/{job_id}`
- Settings: `GET/POST/DELETE /settings/ai-providers`, `GET/POST/DELETE /settings/instagram`
- Ops: `GET /ping`, `GET /status`, `GET /health`

Note: there are **no server-side notification endpoints** — "Watch Later" reminders are scheduled entirely client-side in the mobile app (Expo/Android notification channels), not by this backend.

Interactive docs: `http://localhost:5000/docs` (Swagger) and `/redoc`.

## Git commits

- Do not add Claude, or any `Co-Authored-By: Claude` / Claude Code attribution trailer, to commit messages in this repo.
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, etc.) for commit message subject lines, matching existing history.

## Importance scoring

Every post gets a 1-5 `importance` score (`analyses.importance`, nullable) rating how much lasting/reusable value it has, so posts can be sorted by "worth revisiting" instead of only by recency (`GET /recent?sort=importance`, see `core/database.py:get_recent_light`). This exists specifically so low-value content (memes, pure personal-branding clips) doesn't crowd out genuinely useful content (a taught technique, a well-developed idea) in review.

- **`core/importance.py`** — `IMPORTANCE_PROMPT` + `build_importance_prompt()` + `parse_importance()`. Unlike category/language, importance is **not** spliced into `main.py`'s combined title/summary/tags/music/category/language prompt — it's scored in its own dedicated call (`main.py:score_importance()`, run right after the main analysis for all three pipelines) via `ModelRouter.generate_importance_text()`, which pins the model to **`OPENAI_TEXT_MODEL` specifically** rather than whatever the latency-ranked router hands back for that request (falling back to the normal ranked order only if OpenAI is unavailable/fails). Both the decoupled call and the model pin exist because the original combined-prompt/unpinned-model design produced visibly inconsistent scores between posts of comparable depth. The rubric is deliberately **topic- and format-agnostic** — it scores on depth of payload (a fully-explained technique, or a genuinely developed idea/argument) rather than on subject matter or format, and explicitly guards against charged political/emotional vocabulary (e.g. "hypocrisy," "systemic") reading as depth when no actual mechanism/reasoning is explained. Calibrated against real saved posts, not written in the abstract — see the comment above `IMPORTANCE_PROMPT` for the specific examples that shaped the wording.
- **`TRUSTED_CREATORS`** (also in `core/importance.py`) — a small, explicit, code-level allowlist of usernames whose posts the user has manually confirmed are consistently worth revisiting, independent of any single post's per-post score (the LLM scores each post in isolation with no memory of other posts by the same creator, so this is a deliberate override, not something asked of the model). `apply_trusted_creator_boost()` floors — never lowers — a trusted creator's score at 4. Seeded with `erinmerylstudy`. Applied inside `main.py:score_importance()` for all three pipelines, and again in the backfill script from the post's already-stored `username`.
- Existing posts (saved before this feature, or scored under an older rubric) have `importance IS NULL` or a score from a prior `CURRENT_ANALYSIS_VERSION` — "unscored" is kept distinguishable from "scored low." Run `python scripts/score_importance.py` to backfill only unscored posts, or `python scripts/score_importance.py --force` to re-score every post (e.g. after a rubric/prompt change) — either way it scores from each post's already-stored title/summary/tags/category (no re-download, no full re-analysis) and stamps the post to `CURRENT_ANALYSIS_VERSION` on success, which is what clears it from the review queue.
- This is `CURRENT_ANALYSIS_VERSION` bump **8** — see the version-history comment above the constant and the matching `_seed_changelog()` entry in `core/database.py` for the full description.

## Eloquence scoring

`core/eloquence.py` judges a post's `audio_transcription` for oratory eloquence (`analyses.is_eloquent`/`eloquence_rationale`/`is_tutorial`) — see the module docstring for the rubric. It's a standalone backfill over already-analyzed posts (`scripts/score_eloquence.py`), not part of `CURRENT_ANALYSIS_VERSION`/`main.py`'s pipeline. Candidates are pre-filtered in Python by transcript length (`LENGTH_THRESHOLD`) and filler-word ratio (`passes_prefilter()`) before spending an LLM call.

`scripts/score_eloquence.py` reads `ANALYSIS_MODE` (default `immediate`) exactly like `scripts/rescan_post.py --batch`: `immediate` scores each candidate synchronously via `score_and_stamp_eloquence()`; `ANALYSIS_MODE=batch` instead chunks candidates (`ELOQUENCE_BATCH_CHUNK_SIZE`, default 50) into shared OpenAI Batch API jobs (`router.submit_openai_batch()`, one job per chunk) and returns immediately after submitting. Batch state lives in its own `eloquence_batch_jobs` table (many shortcodes sharing one `batch_id`), advanced by `core/eloquence_batch_processor.py`'s `check_and_advance_eloquence_batches()` — called once on backend startup and on demand via `POST /eloquence/batches/check`, same "no periodic polling" model as the other two batch pipelines (see "Batch mode" and "Rescan pipeline" above). Fully separate table/processor/endpoint from both — eloquence scoring is single-phase (one LLM call, no downstream summary/importance/embedding step), unlike those two.

On a failed/expired/cancelled batch, or a result with no parseable verdict, the pipeline just deletes that shortcode's `eloquence_batch_jobs` row and leaves `is_eloquent` at `NULL` — same "leave it as it was" behavior as the rescan pipeline, since there's no prior eloquence verdict to protect and the post is simply picked up again as an unscored candidate on the next `score_eloquence.py` run.

**Manual override**: `POST /eloquence/override` (`{"shortcodes": [...]}`) is the human-correction path for a batch-scoring false positive. `db.override_eloquence_not_eloquent()` does the actual work per shortcode: if the post is currently `is_eloquent=1`, it logs the AI's prior verdict/rationale/is_tutorial to the append-only `eloquence_overrides` table *before* flipping `is_eloquent` to `False` — the point of keeping this log (rather than just overwriting `eloquence_rationale`) is that a cluster of overrides sharing a similar rationale pattern is the actual signal for what to fix in `ELOQUENCE_PROMPT`, not any single post. A shortcode that's already not eloquent is bucketed as `already_not_eloquent` rather than logged again (nothing was actually corrected), and one that doesn't exist as `not_found`. `GET /eloquence/overrides` reads the log back (newest first) for review.

Driven from `superbrain-web`: `/eloquent`'s `EloquentFeed.tsx` adds a "Select" mode to `InfiniteFeed`/`PostCard` (selection state lives in `EloquentFeed`, not `InfiniteFeed`, so it survives "Load more") and a bulk "Mark N as not eloquent" action, calling `POST /api/eloquence-override` (`src/lib/apiClient.ts`'s `overrideEloquence()`). `/eloquent/overrides` is the review page — a server component that joins `GET /eloquence/overrides`'s log against the cached `/export` payload by shortcode (`fetchEloquenceOverrides()`) so each entry can show the post's title/link alongside the AI's original rationale.

## Study guides

`core/study_guide.py` turns a user-picked set of posts (a selection, search result, theme/cluster, or 3D-space multi-select from `superbrain-web`) into one or more distilled markdown documents, persisted together as a "collection" (`study_guide_collections` + `study_guides` tables) — the "make sense of 2000 saved reels without watching all of them" feature.

- **Pinned to OpenAI specifically, no fallback.** Every call in this feature goes through `ModelRouter.generate_openai_only_text(prompt, STUDY_GUIDE_MODEL)` (`core/model_router.py`) — bypasses the ranked-fallback list entirely (no Groq/Gemini/OpenRouter/Ollama) and raises immediately (HTTP 503 from the route) if `OPENAI_API_KEY` isn't configured or the call fails. `STUDY_GUIDE_MODEL = "gpt-5.6-luna"` is hardcoded in `core/study_guide.py`, independent of the router's usual `OPENAI_TEXT_MODEL` env-driven default. Both are explicit product decisions (made after checking `config/model_rankings.json` showed OpenAI already answering ~all text calls in practice), not technical necessities — don't "helpfully" add fallback back in.
- **`MIN_STUDY_GUIDE_IMPORTANCE = 3`** drops posts scoring below that on the existing importance rubric before synthesis (unscored posts are kept — `NULL` isn't "low"). Duplicated as a matching constant in `superbrain-web/src/lib/ideas.ts` — the two runtimes can't share it directly.
- **`MAX_STUDY_GUIDE_POSTS = 80`** is now a *per-call* chunk size, not a rejection ceiling — see the pipeline below. **`ABSOLUTE_MAX_STUDY_GUIDE_POSTS = 400`** is the real hard ceiling on a whole request (HTTP 400 above it), guarding against an accidental "generate from my entire library" click turning into dozens of paid calls.
- **`generate_study_guide_pipeline(router, posts, groups=None)`** is the actual entry point (`POST /study-guide` calls it via `asyncio.to_thread`). At or under the cap: one call, one guide, `role="final"`. Over the cap — **by explicit user request, not a fallback path** — it runs BOTH a whole-selection pass (`role="full"`, every included post in one call — better at catching connections across the whole set) AND a chunked-then-merged pass (`chunk_posts()` splits along `groups`' semantic boundaries when given — e.g. a theme's micro-clusters, packed greedily up to the per-chunk cap — or evenly positional otherwise; each chunk gets its own call, `role="chunk"`, then `build_merge_prompt()` combines them into `role="merge"`), then `build_reconcile_prompt()` reconciles `full` and `merge` into `role="final"`. **Every intermediate guide is persisted, none are deleted** — the user explicitly wants to inspect how the final guide was built, not just trust it. Guides come back ordered `final, full, merge, chunk, chunk, ...` (`position` 0, 1, 2, 3+).
- **Dedup is still entirely prompt-based, no claim extraction/chunk embeddings** — read the module docstring before touching it. The multi-call pipeline patches the *within-one-prompt* size limit, but recurrence-counting across chunks is still only as good as what the merge/reconcile prompts can infer from already-condensed guide text, not real per-post citation tallying. That's the same v1 gap called out in `superbrain-web/src/lib/ideas.ts` and still the planned v2 (atomic claim extraction + chunk-level embeddings) — not implemented.
- **`core/study_guide_pdf.py`** renders a guide's markdown to PDF (`markdown` + `fpdf2`) and rasterizes page 1 to a PNG thumbnail (`pymupdf`) — both **on demand from the stored `content`**, nothing persisted to disk, via `GET /study-guides/{id}/pdf` and `GET /study-guides/{id}/thumbnail`.
- **Routes**: `POST /study-guide` (body: `shortcodes`, `source_label`, optional `groups: string[][]` for chunk-packing) creates a collection + all its guides in one call. `GET/DELETE /study-guide-collections[/{id}]` for the collection as a whole; `GET/DELETE /study-guides/{id}` for one guide within it (e.g. pruning a single bad chunk without deleting the rest).

## Instagram export import

Two different Instagram "Download Your Information" export shapes are involved, playing deliberately different roles:

- **The "by collection" export** (`saved_collections.json`-shaped — a top-level list of collections, each with its posts nested inside, parsed by `extract_meta_label_values_shape()`) decides **what** gets analyzed and which SuperBrain collection(s) it's assigned to. Only posts saved in a collection are ever imported this way — there is no path that analyzes a post found only in the export below.
- **The "all posts" export** (`saved_posts.json`-shaped — a flat, ungrouped list where every entry carries its own real `timestamp`, parsed by `extract_post_timestamps()`, a genuinely different shape that `extract_meta_label_values_shape()` doesn't recognize) is used **only** as a lookup table for each analyzed post's real save date. A post that's in this file but not in the collections file is never analyzed on its own.

`analyses.date_saved` (nullable TEXT) holds that real save date — verified (not assumed) to actually be a save date and not a duplicate of the content's publish date: cross-checked against `analyses.post_date` (independently scraped from Instagram's own post metadata via `instaloader`'s `post.date_utc`, `instagram/instagram_downloader.py`), `date_saved` is always *later* than `post_date`, by a wildly varying amount (a day to several months) — the signature of "whenever I happened to see and save this," not a second copy of the same publish fact.

- **Historical backfill**: `scripts/backfill_date_saved.py <saved_posts.json>` — matches the all-posts file's timestamps against already-imported posts by shortcode and sets `date_saved` directly via `db.update_date_saved()`. No collection grouping needed, unlike the retired `saved_order` approach below.
- **Live imports**: `scripts/import_saved_instagram.py` (and its `_by_collection` sibling) take the collections file positionally and an optional `--all-posts-file` for the lookup. `date_saved` is threaded through **exactly like `caption`/`hashtags`** — `AnalyzeRequest.date_saved` → a migrated `processing_queue.date_saved` column (so a request that has to wait in the queue doesn't lose it) → both subprocess-spawn sites' `--date-saved` CLI arg → `main.py`'s argv parsing → `save_analysis()`'s `date_saved` param. Every client ignores this field except these import scripts, same as caption/hashtags already are. `save_analysis()` protects it from being blanked on omission (`CASE WHEN excluded.date_saved IS NOT NULL ...`, same treatment as `embedding`/`media_files`/`importance`/`caption`) — without that, the rescan pipeline (which calls `save_analysis()` with no `date_saved` context) would silently wipe it on every re-analysis.
- **`GET /recent?sort=date_saved`** and superbrain-web's Browse "Save date" sort put `date_saved`-known rows first (ascending), then fall through to `analyzed_at` ascending for every other post — one continuous oldest-to-newest timeline. **`sort=post_date`** is the same shape keyed on the content's own publish date instead — a distinct axis ("when was this posted" vs. "when did I save it"), needing no backfill since `post_date` is already populated at analysis time for essentially every Instagram post.
- **`--reverse-collections` (both import scripts) now defaults to OFF.** It used to default on and be load-bearing for `analyzed_at` accuracy; now that real dates come from the all-posts file regardless of analysis order, it's purely an optional "analyze this collection oldest-first instead" preference (`reverse_within_collections()` in `import_saved_instagram.py` still does the actual reversal, groups parsed records by collection and reverses each one's internal slice, unfixed cross-category — nothing about that logic changed, only the default). Off by default means the newest-saved reels in each collection get analyzed, and become searchable, first.
- **`analyses.saved_order`** (nullable INTEGER) is **retired** — a reconstructed relative rank from before `date_saved` existed, back when the only signal available was each collection's newest-first ordering. Column kept (this codebase's migrations are additive-only) but no longer populated or read anywhere; every row was reset to NULL when `date_saved` replaced it. `scripts/backfill_saved_order.py` is deleted.
- **Skip the artificial per-item delay on a cache hit.** `/analyze`'s response always includes `cached: true/false`. The import scripts now check it and skip `time.sleep(random.uniform(delay_min, delay_max))` when `cached` is true — no real work happened (no download, no AI calls), so there's nothing to throttle. A failed attempt still sleeps as before.
- **`POST /instagram-export/jobs`** (+ `GET .../jobs`, `GET .../jobs/{id}`, `POST .../preview`) is what superbrain-web's `/import` page drives to run either import script from the browser instead of a terminal, now accepting both files (`export_data` + optional `all_posts_data`). Deliberately a distinct URL prefix from `/import`/`/import/file` above — those restore a SuperBrain-format `/export` backup (`ImportData`), a completely different operation from ingesting a fresh Instagram export and running it through the full analysis pipeline. A job spawns the chosen script as a subprocess from a background thread (same `PYTHONUNBUFFERED=1` requirement as `_run_rescan_subprocess()`, since a full run can take hours and the caller needs `log_tail` to actually stream rather than sit empty until the process exits) and is tracked in the `import_jobs` table; only one job may run at a time (409 otherwise) since both scripts share the same resumable `scripts/import_state.json`. A job still `status='running'` after a server restart is stale (its subprocess died with the old process) and gets flipped to `'failed'` on the next startup — `import_state.json` isn't affected, so simply starting a new job against the same file(s) resumes where it left off.
- **The uploaded JSON is structurally validated, not just parsed.** `AnalyzeExportPreviewRequest`/`InstagramExportJobCreate`'s `export_data`/`all_posts_data` fields are typed `Any` — Pydantic only guarantees "valid JSON", not "the right shape" — so `_validate_instagram_export_shapes()` (`api.py`) checks each against `scripts/import_saved_instagram.py`'s `looks_like_collections_export()`/`looks_like_all_posts_export()` before anything is written to disk or handed to a subprocess, rejecting a mismatched/garbage upload with HTTP 400 and a specific message. This is deliberately checked **twice**, independently: once here in the backend (the actual authority), and again in superbrain-web's own Route Handlers (`src/lib/instagramExportValidation.ts`, mirrored TS logic, same distinguishing signal — a top-level item's `label_values` containing `Name` vs. containing `URL` directly, since both export shapes can carry a top-level `timestamp` field) — because a request can reach either layer directly, bypassing whatever the browser page itself does. Keep the two implementations in sync if either shape-detection rule changes.
