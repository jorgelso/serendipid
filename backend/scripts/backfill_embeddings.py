#!/usr/bin/env python3
"""
One-off backfill: generate embeddings for posts that were analyzed before
embedding generation was wired into main.py's save step.

Does NOT re-download or re-run AI analysis — it only reads each post's
already-stored title/summary/tags and generates an embedding from that,
then updates just the embedding column.

Usage:
    cd backend
    .venv/bin/python scripts/backfill_embeddings.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.model_router import get_router


def main() -> None:
    db = get_db()
    router = get_router()

    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    rows = db.get_posts_missing_embedding()

    if not rows:
        print("Nothing to backfill — every post already has an embedding.")
        return

    print(f"Backfilling embeddings for {len(rows)} post(s)...")

    ok = fail = 0
    for i, row in enumerate(rows, start=1):
        shortcode = row["shortcode"]
        embedding_text = f"{row['title'] or ''}\n\n{row['summary'] or ''}\n\nTags: {', '.join(row['tags'])}"
        print(f"[{i}/{len(rows)}] {shortcode} ...", end=" ", flush=True)

        embedding = router.generate_embedding(embedding_text)
        if embedding:
            db.update_embedding(shortcode, embedding)
            ok += 1
            print(f"OK ({len(embedding)} dims)")
        else:
            fail += 1
            print("FAILED (no embedding returned — check OPENAI_API_KEY / rate limits)")

    print(f"\nDone. {ok} succeeded, {fail} failed.")


if __name__ == "__main__":
    main()
