#!/usr/bin/env python3
"""
Backfill eloquence scores for existing posts — see core/eloquence.py for the
rubric and rationale.

Candidates are posts with a transcript longer than core.eloquence.
LENGTH_THRESHOLD chars, further narrowed in Python by filler-word ratio
(core.eloquence.passes_prefilter()) before any LLM call is spent — both
thresholds were validated by hand against real labeled posts during
development, not chosen arbitrarily. Posts already scored (is_eloquent IS
NOT NULL) are skipped by default so re-running this script doesn't re-spend
LLM calls on posts it's already judged.

Writes straight to the database (is_eloquent, eloquence_rationale,
is_tutorial) as it scores each post — there is no dry-run/print-only mode
here; use scripts/validate_eloquence.py (or a one-off snippet) for that.

Usage:
    cd backend
    .venv/bin/python scripts/score_eloquence.py            # only unscored candidates
    .venv/bin/python scripts/score_eloquence.py --force     # re-score every candidate
                                                               # (e.g. after a rubric change)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.eloquence import LENGTH_THRESHOLD, passes_prefilter, score_and_stamp_eloquence


def main() -> None:
    force = "--force" in sys.argv

    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    rows = db.get_posts_for_eloquence_scoring(LENGTH_THRESHOLD, include_scored=force)
    candidates = [r for r in rows if passes_prefilter(r["audio_transcription"])]

    skipped_by_filler = len(rows) - len(candidates)
    print(
        f"{len(rows)} post(s) over {LENGTH_THRESHOLD} chars"
        f"{' (rescoring all)' if force else ' and unscored'}; "
        f"{skipped_by_filler} skipped by filler-ratio pre-filter; "
        f"scoring {len(candidates)}."
    )

    if not candidates:
        print("Nothing to score.")
        return

    ok = fail = 0
    for i, row in enumerate(candidates, start=1):
        shortcode = row["shortcode"]
        print(f"[{i}/{len(candidates)}] {shortcode} — {row['title']!r} ...", end=" ", flush=True)

        is_eloquent = score_and_stamp_eloquence(db, shortcode, row["audio_transcription"])
        if is_eloquent is None:
            fail += 1
            print("FAILED (no parseable verdict returned)")
        else:
            ok += 1
            print("ELOQUENT" if is_eloquent else "not eloquent")

    print(f"\nDone. {ok} succeeded, {fail} failed.")


if __name__ == "__main__":
    main()
