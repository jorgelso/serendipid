# SuperBrain Web

A discovery site over posts analyzed by the SuperBrain backend — type an interest and see what
you've saved about it, or browse themes the site notices on its own (e.g. separate guitar, violin,
and piano reels grouped under one "musical instruments" theme) by clustering the backend's stored
embeddings. Talks to the backend only over HTTP; never reads or modifies anything under `backend/`,
so the backend can run on the same machine or a different one. Read-only — editing/hiding posts
stays in `superbrain-dashboard/`.

## Setup

```bash
cd superbrain-web
npm install
cp .env.example .env.local
```

Edit `.env.local`:
- `SUPERBRAIN_API_URL` — base URL of the running backend (e.g. `http://127.0.0.1:5050`).
- `SUPERBRAIN_API_KEY` — the token from `backend/token.txt` on the machine running the backend.

## Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Pages

- **Home** — themes the site has automatically detected across your saved posts (two-pass
  clustering over embeddings: tight micro-clusters first, then merged into broader themes), plus
  everything that hasn't joined a theme yet, grouped by category.
- **Search** (`/search?q=...`) — semantic search by topic/meaning via the backend's
  `/search/semantic` endpoint, not keyword matching.

Both pages load post content (thumbnails, full analysis text) on demand as you expand a
theme/category — the initial page only ever contains labels and counts, so it stays fast
regardless of how large your library gets.

## Rescan library

The "Rescan library" button re-fetches posts from the backend and recomputes themes. Nothing
auto-refreshes in the background — click it after your saved library changes.

## Tuning clustering

`src/lib/clustering.ts`'s `DEFAULT_OPTIONS` (`fineThreshold`, `coarseThreshold`, `minThemeSize`)
control how aggressively posts get grouped. These were tuned against a small, early slice of a
much larger library (import still in progress) — revisit them as more posts get analyzed.
