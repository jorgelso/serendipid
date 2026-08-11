#!/usr/bin/env python3
"""
Backfill/re-score importance (1-5) for existing posts — see core/importance.py
and the CURRENT_ANALYSIS_VERSION history in core/database.py.

Does NOT re-download or re-run the full analysis pipeline — it only reads
each post's already-stored title/summary/tags/category and asks the model to
score that, then updates just the importance column (and stamps
analysis_version so the post drops out of the 'needs_review' queue).

Usage:
    cd backend
    .venv/bin/python scripts/score_importance.py            # only unscored posts
    .venv/bin/python scripts/score_importance.py --force     # re-score every post
                                                               # (e.g. after a rubric change)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.importance import score_and_stamp_importance


def main() -> None:
    force = "--force" in sys.argv

    db = get_db()

    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    rows = db.get_posts_missing_importance(include_scored=force)

    if not rows:
        print("Nothing to backfill — every post already has an importance score.")
        return

    verb = "Re-scoring" if force else "Backfilling"
    print(f"{verb} importance scores for {len(rows)} post(s)...")

    ok = fail = 0
    for i, row in enumerate(rows, start=1):
        shortcode = row["shortcode"]
        print(f"[{i}/{len(rows)}] {shortcode} ...", end=" ", flush=True)

        importance = score_and_stamp_importance(
            db, shortcode, row["title"], row["summary"], row["tags"], row["category"], row["username"]
        )
        if importance is None:
            fail += 1
            print("FAILED (no parseable score returned)")
        else:
            ok += 1
            print(f"OK ({importance}/5)")

    print(f"\nDone. {ok} succeeded, {fail} failed.")


if __name__ == "__main__":
    main()
