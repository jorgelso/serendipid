# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SuperBrain — a self-hosted, AI-powered "second brain": share an Instagram post, YouTube video, or web page from any app, and a local backend analyzes it with AI (summary, category, tags, transcription, background-music ID) so it becomes searchable and organized instead of disappearing into a platform's save list. Everything is stored locally (SQLite) — no cloud service, no vendor lock-in. Licensed AGPL-3.0.

## Repo layout

This is a single git repository (monorepo) containing multiple independent packages — there is no separate frontend repo and no submodules. Each package has its own dependency manifest and is developed independently; nothing here is a shared build/workspace (no root `package.json`, no Lerna/Turborepo/Nx).

| Package | Stack | Role |
|---|---|---|
| `backend/` | Python 3 / FastAPI / SQLite | The only server. All clients below talk to it over HTTP. See `backend/CLAUDE.md`. |
| `superbrain-app/` | React Native (Expo SDK 54) | **Primary client** — Android app, receives shared URLs via the OS share sheet, schedules local notifications. |
| `superbrain-web/` | Next.js / TypeScript | Secondary client — browser-based viewer/search/light-editing UI. See `superbrain-web/CLAUDE.md`. |
| `superbrain-dashboard/` | Python / Streamlit | Analytics dashboard (charts over the `/export` data) — read-oriented, not for content ingestion. |
| `superbrain-cli/` (npm: `superbrain-server`) | Node.js | Cross-platform installer/launcher — `npx superbrain-server` downloads and runs the backend without cloning this repo. |
| `superbrain-extension/` | Manifest V3 browser extension | Imports Instagram saved posts/collections into SuperBrain from the browser. |
| `docs/` | Markdown | Architecture notes, audits, changelog. |

Only `backend/` and `superbrain-web/` have their own `CLAUDE.md` today; the other packages are small enough that this file's overview should suffice.

## Big-picture architecture

Every client (mobile app, web viewer, dashboard, browser extension) is a thin consumer of one FastAPI backend — they never talk to each other or share code, and all cross-package coordination happens through the backend's REST API and its SQLite database. Auth across all of them is a single shared secret: the backend generates an access token (`backend/token.txt`) on first run, and every client sends it as the `X-API-Key` header.

Within the backend itself, the one architectural detail worth knowing before touching anything: `api.py` (the FastAPI app) does not call the analysis pipeline in-process for Instagram posts — it spawns `main.py` as a subprocess per request so a crash or hang in one analysis can't take down the API server. YouTube and webpage analysis, by contrast, run in-process. See `backend/CLAUDE.md` for the full breakdown (routes, DB schema/migration pattern, the multi-provider AI Model Router with automatic fallback and latency-based ranking).

`superbrain-web/src/types/domain.ts` and the mobile app's `src/types/index.ts` each independently mirror the backend's response shapes (`/export`, `/search/semantic`, the `analyses` table) — there's no shared types package, so a backend schema change means updating both clients' type files by hand.

## Deployment model: backend and clients are independent hosts, not a coupled local stack

Nothing in this codebase assumes the backend and any client run on the same machine — they only ever talk over HTTP with a URL + API key, so each piece is meant to be deployable on its own host:

- **`backend/`** is the one thing that has to run somewhere persistent (a home PC, Raspberry Pi, or a VPS — see the "Hosting Options" table in root `README.md`). It's a plain Uvicorn/FastAPI process; nothing about it is tied to `localhost`.
- **`superbrain-web/`** talks to the backend exclusively from server-side code (`SUPERBRAIN_API_URL`/`SUPERBRAIN_API_KEY`, read in `src/lib/config.ts`, never exposed to the browser). That means it can be deployed anywhere Next.js runs (Vercel, a VPS, etc.) *separately* from the backend — just point `SUPERBRAIN_API_URL` at wherever the backend is actually reachable (a public IP/domain, or a tunnel like ngrok if it's behind NAT). There is no code path that assumes the two are co-located.
- **`superbrain-app/`** (mobile) and **`superbrain-extension/`** are configured with the backend URL/token by the user at runtime (app Settings screen / extension popup), so the same "backend can be anywhere" rule applies to them too.

Two things to actually configure when the backend stops being `localhost` for every client:
- **CORS** — `backend/api.py` defaults `ALLOWED_ORIGINS` to `"*"` (open, no credentials) when that env var is unset, which is fine for local dev but should be set to the deployed web frontend's actual origin(s) once it's hosted separately, so cookies/credentialed requests aren't silently disabled.
- **Reachability** — the backend must be reachable from wherever each client is deployed: a public port/domain, a reverse proxy, or a tunnel (ngrok is what the README uses for phone access today). `SUPERBRAIN_API_URL` (web) and the app's Settings screen (mobile) are the only places this address is configured — there's no hardcoded backend host anywhere in client code.

### Running everything locally (dev)

```bash
# 1. Backend
cd backend && python start.py     # first-run wizard: venv, deps, API keys, launches on :5000

# 2. Web viewer (optional)
cd superbrain-web && npm install && cp .env.example .env.local
# set SUPERBRAIN_API_URL=http://localhost:5000 and SUPERBRAIN_API_KEY=<backend/token.txt contents>
npm run dev

# 3. Mobile app (optional, needs Expo tooling)
cd superbrain-app && npm install && npx expo start
```

Docker (`backend/start-docker.sh` / `start-docker-prod.sh`) is the alternative to `start.py` for the backend, and is generally the better fit once the backend moves to a server rather than a dev machine; see `backend/CLAUDE.md` for the dev/prod variants.

## Contributing / releases

Standard fork → feature branch → PR flow (see root `README.md`). Pushes to `main` trigger `.github/workflows/build.yml`, which builds the Android APK, attaches it to the `latest` GitHub release, and publishes the `superbrain-server` npm/GitHub package — this is automatic, not something you trigger manually per change.

## Git commits

- Do not add Claude, or any `Co-Authored-By: Claude` / Claude Code attribution trailer, to commit messages in this repo.
- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, etc.) for commit message subject lines, matching existing history.
