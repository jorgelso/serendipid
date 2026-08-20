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
LLM calls on posts it's already judged. Posts with an eloquence batch job
already in flight (--batch mode) are also skipped, so a re-run while a batch
is pending doesn't submit duplicate requests for the same shortcode.

Two modes, same candidate selection, picked by ANALYSIS_MODE (default
"immediate") exactly like scripts/rescan_post.py --batch:
  - immediate: scores each candidate synchronously via score_and_stamp_eloquence()
    (regular OpenAI API), writing straight to the database as it goes.
  - batch: submits candidates to OpenAI's Batch API instead — ~50% cheaper,
    in exchange for turnaround of minutes up to 24h. Candidates are chunked
    (ELOQUENCE_BATCH_CHUNK_SIZE, default 50) into separate shared batch jobs
    rather than one giant job, so a chunk becomes a durable checkpoint
    (core/eloquence_batch_processor.py, eloquence_batch_jobs table) as soon
    as it's submitted instead of nothing being safe until the whole backfill
    finishes. Submission only; results are picked up later by
    core.eloquence_batch_processor.check_and_advance_eloquence_batches(),
    called on backend startup and via POST /eloquence/batches/check — same
    "no periodic polling" model as the other two batch pipelines.

There is no dry-run/print-only mode here; use scripts/validate_eloquence.py
(or a one-off snippet) for that.

Usage:
    cd backend
    .venv/bin/python scripts/score_eloquence.py                       # only unscored candidates
    .venv/bin/python scripts/score_eloquence.py --force                # re-score every candidate
                                                                          # (e.g. after a rubric change)
    ANALYSIS_MODE=batch .venv/bin/python scripts/score_eloquence.py    # submit candidates as OpenAI batch jobs
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.eloquence import LENGTH_THRESHOLD, passes_prefilter, score_and_stamp_eloquence, build_eloquence_batch_request

# See scripts/rescan_post.py's OPENAI_BATCH_CHUNK_SIZE for the same rationale:
# chunking gives each chunk a durable checkpoint as soon as it's submitted,
# instead of nothing being safe until an entire (possibly 800+ post) backfill
# finishes submitting.
BATCH_CHUNK_SIZE = int(os.getenv("ELOQUENCE_BATCH_CHUNK_SIZE", "50"))


def _select_candidates(db, force: bool):
    rows = db.get_posts_for_eloquence_scoring(LENGTH_THRESHOLD, include_scored=force)
    pending = {j["shortcode"] for j in db.get_eloquence_batch_jobs()}
    not_pending = [r for r in rows if r["shortcode"] not in pending]
    candidates = [r for r in not_pending if passes_prefilter(r["audio_transcription"])]
    print(
        f"{len(rows)} post(s) over {LENGTH_THRESHOLD} chars"
        f"{' (rescoring all)' if force else ' and unscored'}; "
        f"{len(rows) - len(not_pending)} skipped (batch already in flight); "
        f"{len(not_pending) - len(candidates)} skipped by filler-ratio pre-filter; "
        f"{len(candidates)} candidate(s)."
    )
    return candidates


def run_immediate(db, candidates: list) -> None:
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


def run_batch(db, candidates: list) -> None:
    from core.model_router import get_router

    router = get_router()
    submitted = 0
    for start in range(0, len(candidates), BATCH_CHUNK_SIZE):
        chunk = candidates[start:start + BATCH_CHUNK_SIZE]
        requests_list = [
            build_eloquence_batch_request(row["shortcode"], row["audio_transcription"])
            for row in chunk
        ]
        batch_id = router.submit_openai_batch(requests_list, endpoint="/v1/chat/completions")
        db.enqueue_eloquence_batch_jobs([row["shortcode"] for row in chunk], batch_id)
        submitted += len(chunk)
        print(f"  chunk {start // BATCH_CHUNK_SIZE + 1}: {len(chunk)} post(s) -> batch {batch_id}")

    print(
        f"\nSubmitted {submitted} post(s) across "
        f"{(len(candidates) + BATCH_CHUNK_SIZE - 1) // BATCH_CHUNK_SIZE} batch job(s). "
        f"Results are picked up on the next backend startup or POST /eloquence/batches/check."
    )


def main() -> None:
    force = "--force" in sys.argv
    analysis_mode = os.getenv("ANALYSIS_MODE", "immediate").strip().lower()

    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    candidates = _select_candidates(db, force)
    if not candidates:
        print("Nothing to score.")
        return

    if analysis_mode == "batch":
        run_batch(db, candidates)
    else:
        run_immediate(db, candidates)


if __name__ == "__main__":
    main()
