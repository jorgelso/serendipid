# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Serendipid is a self-hosted, AI-powered archive for saved content, built mainly for Instagram reels (YouTube videos and web pages are supported too). A local backend analyzes each post with AI (summary, categories, tags, transcription, background-music ID, importance score) so it becomes searchable and organized instead of disappearing into a platform's save list. Everything is stored locally (SQLite). Licensed AGPL-3.0; originally forked from SuperBrain (see the root README's credits).

## Repo layout

This is a single git repository (monorepo) containing multiple independent packages — there is no separate frontend repo and no submodules. Each package has its own dependency manifest and is developed independently; nothing here is a shared build/workspace (no root `package.json`, no Lerna/Turborepo/Nx).

| Package | Stack | Role |
|---|---|---|
| `backend/` | Python 3 / FastAPI / SQLite | The only server. All clients below talk to it over HTTP. See `backend/CLAUDE.md`. |
| `serendipid-web/` | Next.js / TypeScript | **Primary client**: browse/search/chat/study guides/imports UI, behind a password login. See `serendipid-web/CLAUDE.md`. |
| `serendipid-ios/` | SwiftUI (XcodeGen `project.yml`) | Native iOS app + share extension. Behind the backend's current auth model (see `TODO.md`). |
| `serendipid-extension/` | Manifest V3 browser extension | Imports Instagram saved posts/collections into Serendipid from the browser. |
| `docs/` | Markdown | Architecture, configuration, deployment, changelog. |

Only `backend/` and `serendipid-web/` have their own `CLAUDE.md`; the other packages are small enough that this file's overview should suffice.

## Big-picture architecture

Every client (web app, iOS app, browser extension) is a thin consumer of one FastAPI backend — they never talk to each other or share code, and all cross-package coordination happens through the backend's REST API and its SQLite database. Auth across all of them is a single shared secret: the backend generates an access token (`backend/token.txt`) on first run, and every client sends it as the `X-API-Key` header.

Within the backend itself, the one architectural detail worth knowing before touching anything: `api.py` (the FastAPI app) does not call the analysis pipeline in-process for Instagram posts — it spawns `main.py` as a subprocess per request so a crash or hang in one analysis can't take down the API server. YouTube and webpage analysis, by contrast, run in-process. See `backend/CLAUDE.md` for the full breakdown (routes, DB schema/migration pattern, the multi-provider AI Model Router with automatic fallback and latency-based ranking).

`serendipid-web/src/types/domain.ts` and the iOS app's `SerendipidCore/Sources/SerendipidCore/Models/` each independently mirror the backend's response shapes (`/export`, `/search/semantic`, the `analyses` table) — there's no shared types package, so a backend schema change means updating both clients' type files by hand.

## Deployment model: backend and clients are independent hosts, not a coupled local stack

Nothing in this codebase assumes the backend and any client run on the same machine — they only ever talk over HTTP with a URL + API key, so each piece is meant to be deployable on its own host:

- **`backend/`** is the one thing that has to run somewhere persistent (a home PC, Raspberry Pi, or a VPS — see "Hosting on a Raspberry Pi" in root `README.md`). It's a plain Uvicorn/FastAPI process; nothing about it is tied to `localhost`.
- **`serendipid-web/`** talks to the backend exclusively from server-side code (`SERENDIPID_API_URL`/`SERENDIPID_API_KEY`, read in `src/lib/config.ts`, never exposed to the browser). Media and thumbnails are proxied too (`src/app/api/media`, `src/app/api/backend-static`), so browsers never contact the backend, and every route sits behind `src/proxy.ts`'s `WEB_PASSWORD` session check. That means it can be deployed anywhere Next.js runs (Vercel, a VPS, etc.) *separately* from the backend — just point `SERENDIPID_API_URL` at wherever the backend is actually reachable (a public IP/domain, or a tunnel like ngrok if it's behind NAT). There is no code path that assumes the two are co-located.
- **`serendipid-ios/`** and **`serendipid-extension/`** are configured with the backend URL/token by the user at runtime (app Settings screen / extension options page), so the same "backend can be anywhere" rule applies to them too.

Two things to actually configure when the backend stops being `localhost` for every client:
- **CORS** — `backend/api.py` defaults `ALLOWED_ORIGINS` to `"*"` (open, no credentials) when that env var is unset, which is fine for local dev but should be set to the deployed web frontend's actual origin(s) once it's hosted separately, so cookies/credentialed requests aren't silently disabled.
- **Reachability** — the backend must be reachable from wherever each client is deployed: a private network (Tailscale), a reverse proxy, or a tunnel. `SERENDIPID_API_URL` (web) and the app's Settings screen (iOS) are the only places this address is configured — there's no hardcoded backend host anywhere in client code.

### Running everything locally (dev)

```bash
# 1. Backend
cd backend && python start.py     # first-run wizard: venv, deps, API keys, launches on :5050

# 2. Web viewer (optional)
cd serendipid-web && npm install && cp .env.example .env.local
# set SERENDIPID_API_URL=http://localhost:5050, SERENDIPID_API_KEY=<backend/token.txt contents>, WEB_PASSWORD=<anything>
npm run dev

# 3. iOS app (optional, needs Xcode + XcodeGen)
cd serendipid-ios && xcodegen generate && open Serendipid.xcodeproj
```

Docker (`backend/start-docker.sh` / `start-docker-prod.sh`) is the alternative to `start.py` for the backend, and is generally the better fit once the backend moves to a server rather than a dev machine; see `backend/CLAUDE.md` for the dev/prod variants.

## Contributing / releases

Standard fork → feature branch → PR flow (see root `README.md`). There are no CI workflows or published packages; the backend is run from a clone (or Docker), not installed from a registry.

## Configuration

Categories, languages, trusted authors/creators, excluded/sensitive Instagram folders and the import priority folder are not hardcoded: they come from `backend/core/default_config.json` (committed defaults) overridden by `backend/config/user_config.json` (gitignored), loaded by `backend/core/app_config.py`. Don't reintroduce hardcoded lists of these; add a config key instead. See `docs/CONFIGURATION.md`.

## Git commits

- Do not add Claude, or any `Co-Authored-By: Claude` / Claude Code attribution trailer, to commit messages in this repo.
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, etc.) for commit message subject lines, matching existing history.
