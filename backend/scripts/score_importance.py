#!/usr/bin/env python3
"""
One-off backfill: score importance (1-5) for posts that were analyzed before
importance scoring was wired into main.py's save step — see
core/importance.py and CURRENT_ANALYSIS_VERSION == 6 in core/database.py.

Does NOT re-download or re-run the full analysis pipeline — it only reads
each post's already-stored title/summary/tags/category and asks the model to
score that, then updates just the importance column (and stamps
analysis_version so the post drops out of the 'needs_review' queue).

Usage:
    cd backend
    .venv/bin/python scripts/score_importance.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.model_router import get_router
from core.importance import IMPORTANCE_PROMPT, parse_importance, apply_trusted_creator_boost


def main() -> None:
    db = get_db()
    router = get_router()

    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    rows = db.get_posts_missing_importance()

    if not rows:
        print("Nothing to backfill — every post already has an importance score.")
        return

    print(f"Backfilling importance scores for {len(rows)} post(s)...")

    ok = fail = 0
    for i, row in enumerate(rows, start=1):
        shortcode = row["shortcode"]
        print(f"[{i}/{len(rows)}] {shortcode} ...", end=" ", flush=True)

        prompt = f"""TITLE: {row['title'] or ''}

SUMMARY: {row['summary'] or ''}

TAGS: {', '.join(row['tags'])}

CATEGORY: {', '.join(row['category'])}

{IMPORTANCE_PROMPT}"""

        response = router.generate_text(prompt)
        importance = parse_importance(response) if response else None

        if importance is None:
            fail += 1
            print("FAILED (no parseable score returned)")
            continue

        importance = apply_trusted_creator_boost(importance, row["username"])
        db.update_importance(shortcode, importance)
        ok += 1
        print(f"OK ({importance}/5)")

    print(f"\nDone. {ok} succeeded, {fail} failed.")


if __name__ == "__main__":
    main()
