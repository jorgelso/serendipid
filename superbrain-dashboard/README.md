# SuperBrain Dashboard

A local Streamlit dashboard for browsing, searching, and lightly editing posts
analyzed by the SuperBrain backend. This is a standalone app that talks to the
backend only over HTTP — it never reads or modifies anything under `backend/`,
so the backend can run on the same machine or a different one.

## Setup

```bash
cd superbrain-dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `SUPERBRAIN_API_URL` — base URL of the running backend (e.g. `http://127.0.0.1:5050`).
- `SUPERBRAIN_API_KEY` — the token from `backend/token.txt` on the machine running the backend.

## Run

```bash
streamlit run Home.py
```

## Pages

- **Home** — overview metrics and category/collection breakdown.
- **Browse** — filter posts by category, collection, or tag; view full analysis
  fields; edit category/title/summary inline; hide a post (soft-delete — see
  caveat below).
- **Search** — semantic search by topic/meaning (via the backend's
  `/search/semantic` endpoint), not just keyword matching.
- **Insights** — category/collection/tag breakdowns, plus a semantic
  instructional-vs-self-improvement content split with a tunable confidence
  threshold.

## Note on "Hide post"

Hiding a post calls the backend's `DELETE /post/{shortcode}`, which sets
`is_hidden=1` server-side. The post's data is kept (not erased), but there is
no "unhide" endpoint anywhere in the backend API, so this cannot be undone
from this dashboard once confirmed.
