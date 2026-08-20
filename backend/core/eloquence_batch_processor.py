#!/usr/bin/env python3
"""
Resumption logic for scripts/score_eloquence.py --batch under
ANALYSIS_MODE=batch. Fully separate from core/batch_processor.py and
core/rescan_batch_processor.py — eloquence scoring is a one-call-per-post
backfill over posts that already have a stored analysis, so there's no
downstream summary/importance/embedding phase to advance through, unlike
those two pipelines. Many shortcodes share one batch_id (one shared OpenAI
batch job per chunk submitted by scripts/score_eloquence.py), so advancing
still has to fetch each shared batch's status/results once and fan them back
out to every shortcode in the group, not repeat the same OpenAI call per row.

Single-phase lifecycle per shortcode (eloquence_batch_jobs table,
core/database.py): a row exists while its batch is in flight, and is deleted
on resolution (success or failure) — there's no phase column to advance.
Called in-process from api.py: once on backend startup, and on demand via
POST /eloquence/batches/check.

On any per-shortcode failure (batch failed/expired/cancelled, or a result
with no parseable verdict), this module never touches the analyses row —
is_eloquent simply stays NULL, so the post is picked up again as an unscored
candidate the next time scripts/score_eloquence.py runs. Same "leave it as it
was" behavior as core/rescan_batch_processor.py, for the same reason: there's
nothing to roll back to, just nothing gained yet.
"""

import threading
from collections import defaultdict

from core.database import get_db
from core.model_router import get_router
from core.eloquence import parse_eloquence

_lock = threading.Lock()

_TERMINAL_OK = {"completed"}
_TERMINAL_BAD = {"failed", "expired", "cancelled"}
_TERMINAL = _TERMINAL_OK | _TERMINAL_BAD


def check_and_advance_eloquence_batches() -> dict:
    if not _lock.acquire(blocking=False):
        return {"skipped": "an eloquence batch check is already running"}
    try:
        db = get_db()
        scored, failed, still_waiting = [], [], []

        by_batch = defaultdict(list)
        for job in db.get_eloquence_batch_jobs():
            by_batch[job["batch_id"]].append(job)

        for batch_id, jobs in by_batch.items():
            try:
                s, f, w = _advance_batch(db, batch_id, jobs)
                scored.extend(s)
                failed.extend(f)
                still_waiting.extend(w)
            except Exception as e:
                print(f"⚠️  [eloquence-batch] check failed for batch {batch_id}: {e}")
                for job in jobs:
                    db.mark_eloquence_batch_job_error(job["shortcode"], str(e))

        return {"scored": scored, "failed": failed, "still_waiting": still_waiting}
    finally:
        _lock.release()


def _fail_job(db, shortcode: str, reason: str):
    print(f"❌ [eloquence-batch] {shortcode}: {reason} — leaving unscored, will retry on next run.")
    db.delete_eloquence_batch_job(shortcode)


def _advance_batch(db, batch_id: str, jobs: list):
    router = get_router()
    status = router.get_batch_status(batch_id)
    batch_status = status.get("status")

    if batch_status in _TERMINAL_BAD:
        for job in jobs:
            _fail_job(db, job["shortcode"], f"shared eloquence batch {batch_status}")
        return [], [j["shortcode"] for j in jobs], []

    if batch_status not in _TERMINAL_OK:
        return [], [], [j["shortcode"] for j in jobs]

    results = router.get_batch_results(batch_id)
    results_by_id = {r.get("custom_id"): r for r in results}

    scored, failed = [], []
    for job in jobs:
        shortcode = job["shortcode"]
        row = results_by_id.get(shortcode)
        raw = router.extract_batch_chat_text(row) if row else None
        is_eloquent, is_tutorial, rationale = parse_eloquence(raw) if raw else (None, None, "")
        if is_eloquent is None:
            _fail_job(db, shortcode, "no parseable verdict in shared eloquence batch result")
            failed.append(shortcode)
            continue

        db.update_eloquence(shortcode, is_eloquent, rationale, is_tutorial=is_tutorial)
        db.delete_eloquence_batch_job(shortcode)
        print(f"✓ [eloquence-batch] {shortcode}: {'ELOQUENT' if is_eloquent else 'not eloquent'}")
        scored.append(shortcode)

    return scored, failed, []
