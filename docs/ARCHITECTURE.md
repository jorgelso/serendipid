# Architecture

## Overview

```
 Instagram export / share sheet / extension
                 │
                 ▼
   ┌──────────────────────────┐        ┌───────────────────┐
   │ backend (FastAPI)        │◀──────▶│ AI providers      │
   │  - analysis pipeline     │        │ OpenAI, Anthropic,│
   │  - SQLite + media files  │        │ Groq, Gemini,     │
   │  - REST API (X-API-Key)  │        │ OpenRouter, Ollama│
   └──────────────────────────┘        └───────────────────┘
        ▲            ▲      ▲
        │ server-side│      │ direct
        │            │      │
 ┌──────────────┐ ┌─────────┐ ┌──────────────┐
 │ serendipid-  │ │ iOS app │ │ Chrome       │
 │ web (Next.js)│ │         │ │ extension    │
 └──────────────┘ └─────────┘ └──────────────┘
        ▲
        │ password session
     browser
```

There is one server, the backend. Every client is a thin consumer of its REST API; clients never talk to each other or share code. All authentication to the backend uses one shared access token sent as the `X-API-Key` header.

The web app calls the backend only from server-side code. It keeps the token in its environment, streams media through its own routes, and protects every page with a password session, so browsers never need to reach the backend.

## Backend

`backend/` is a Python FastAPI application (`api.py`) with a SQLite database (`core/database.py`, plain `sqlite3`, WAL mode).

### Analysis pipeline

- **Instagram posts** are analyzed by `main.py`, which `api.py` runs as a **separate subprocess** for every post. A crash or hang in one analysis cannot take the API down. The pipeline downloads the post, then runs:
  - visual analysis of sampled frames (`analyzers/visual_analyze.py`)
  - audio transcription (`analyzers/audio_transcribe.py`: Groq Whisper, falling back to local Whisper)
  - music identification (`analyzers/music_identifier.py`, Shazam)
  - on-screen and caption text analysis (`analyzers/text_analyzer.py`, `analyzers/caption.py`)
  - a combined summary call producing title, summary, tags, music, categories and language (`core/summary_parser.py`)
  - an importance score with a written justification (`core/importance.py`)
  - an embedding for semantic search

  Downloaded media is moved to `media/<shortcode>/` and kept, so posts can be re-analyzed later without downloading again.
- **YouTube videos** run in-process through Gemini's native video understanding (`analyzers/youtube_analyzer.py`).
- **Web pages** run in-process: the text is extracted (trafilatura, newspaper4k) and summarized (`analyzers/webpage_analyzer.py`).

Only one Instagram analysis runs at a time. Extra requests wait in a persistent queue (`processing_queue`). Posts Instagram refuses to serve are retried automatically after a delay, and can be uploaded by hand from the web app's Admin page.

### Model router

`core/model_router.py` holds an ordered list of models per task (text, vision, chat) across providers. Each call tries the best-ranked available model and falls through on errors or rate limits; failing models are cooled down, and ranking adapts to measured latency. State is kept in `config/model_rankings.json`. New AI-backed features should go through the router rather than calling a provider directly.

A few features currently call OpenAI directly with no fallback: study guides, importance scoring, embeddings, eloquence scoring and the batch mode described below.

### Batch mode

With `ANALYSIS_MODE=batch`, the OpenAI calls of the Instagram pipeline are sent through OpenAI's Batch API instead of synchronously, at roughly half the cost and with results within 24 hours. There is no polling: pending batches are checked when the backend starts and when you press "Check batches" in the web app.

### Versions and rescans

Every saved post is stamped with the pipeline version that produced it (`CURRENT_ANALYSIS_VERSION`). When the pipeline changes enough to matter, the version is bumped and older posts show up for review. The rescan pipeline (`scripts/rescan_post.py`, `core/rescan_*.py`) redoes only the steps that changed since a post was analyzed, reusing stored media and outputs.

### Configuration

Categories, languages and personal lists come from `core/default_config.json` merged with `config/user_config.json`, loaded by `core/app_config.py`. See [CONFIGURATION.md](CONFIGURATION.md).

### Data model

Main tables:

| Table | Holds |
|---|---|
| `analyses` | One row per post: source URL, metadata, analyzer outputs, summary, tags, categories, language, importance, eloquence, embedding |
| `processing_queue` | Posts waiting for or undergoing analysis, including scheduled retries |
| `collections` | Mirrors Instagram's saved-post collections (created by imports) |
| `boards`, `board_subcollections` | Your own groupings, made in the web app |
| `study_guide_collections`, `study_guides` | Generated study guides and every intermediate step |
| `chat_threads`, `chat_messages` | Chat history |
| `post_views`, `search_queries`, `reels_study_guide` | Signals for recommendations |
| `batch_jobs`, `rescan_batch_jobs`, `eloquence_batch_jobs` | State for pending OpenAI batches |
| `import_jobs` | Instagram export imports started from the web app |
| `deleted_log` | Deleted posts, so clients can sync deletions and re-imports are refused |
| `analysis_changelog` | What changed in each pipeline version |

Schema changes are additive and applied at startup (`ALTER TABLE ... ADD COLUMN` guarded by `try/except`); there is no migration framework.

## Web app

`serendipid-web/` is a Next.js App Router application.

- `src/lib/apiClient.ts` is the only place that calls the backend; `src/lib/config.ts` reads the backend URL and token and must never be imported from client components.
- Client components call the app's own `src/app/api/*` route handlers, which call `apiClient`.
- `src/proxy.ts` checks the session cookie on every request; `src/lib/session.ts` signs and verifies it.
- The full `/export` payload is cached in memory (`src/lib/cache.ts`), and themes and the 3D layout are computed from it (`src/lib/clustering.ts`, `src/lib/vectorSpace.ts`). Mutating routes invalidate the cache.

## iOS app

`serendipid-ios/` is a SwiftUI app generated with XcodeGen (`project.yml`). `SerendipidCore` is a Swift package holding networking, models, caching and the design system; the app and its share extension depend on it. The share extension saves reels straight from Instagram's share sheet and queues them offline when the backend is unreachable. It has not been updated for the current authentication model; see [TODO.md](../TODO.md).

## Browser extension

`serendipid-extension/` is a Manifest V3 Chrome extension that scrolls Instagram's saved page, submits each post to `/analyze`, and mirrors collections through `/collections`.
