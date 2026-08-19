#!/usr/bin/env python3
"""
Resumption logic for scripts/rescan_post.py --batch under ANALYSIS_MODE=batch.
Fully separate from core/batch_processor.py (first-time analysis) — see
backend/CLAUDE.md's "Rescan pipeline" section for why. The one thing this
module does that batch_processor.py doesn't: it's grouping-aware from the
start, because a rescan's whole point is submitting many shortcodes as ONE
shared OpenAI batch job rather than one job per shortcode — so advancing it
has to fetch each shared batch's status/results once and fan them back out
to every shortcode in the group, not repeat the same OpenAI call per row.

Two-phase lifecycle per shortcode (rescan_batch_jobs table, core/database.py),
same shape as batch_jobs: summary_pending -> scoring_pending. Called
in-process from api.py: once on backend startup, and on demand via
POST /rescan/batches/check.

On any per-shortcode failure (batch failed/expired/empty result, or a failed
importance/embedding sub-batch), this module never calls db.queue_for_retry()
and never touches the analyses row — a rescan target already has a good,
saved row from before the rescan was attempted, so a failure just means
"leave it as it was, it'll get picked up on the next rescan attempt." This
is the one deliberate behavioral difference from batch_processor.py's
first-analysis equivalent, which does queue a real retry (correctly, since
there's no prior saved row to fall back to there).
"""

import json
import threading
from collections import defaultdict

from core.database import get_db
from core.model_router import get_router
from core.importance import build_importance_prompt, parse_importance, apply_trusted_creator_boost
from core.summary_parser import parse_summary

_lock = threading.Lock()

_TERMINAL_OK = {"completed"}
_TERMINAL_BAD = {"failed", "expired", "cancelled"}
_TERMINAL = _TERMINAL_OK | _TERMINAL_BAD


def check_and_advance_rescan_batches() -> dict:
    if not _lock.acquire(blocking=False):
        return {"skipped": "a rescan batch check is already running"}
    try:
        db = get_db()
        summary_advanced, summary_failed = [], []
        finalized, still_waiting = [], []

        by_summary_batch = defaultdict(list)
        for job in db.get_rescan_batch_jobs(phase="summary_pending"):
            by_summary_batch[job["summary_batch_id"]].append(job)

        for summary_batch_id, jobs in by_summary_batch.items():
            try:
                advanced, failed, waiting = _advance_summary_group(db, summary_batch_id, jobs)
                summary_advanced.extend(advanced)
                summary_failed.extend(failed)
                still_waiting.extend(waiting)
            except Exception as e:
                print(f"⚠️  [rescan-batch] summary-phase check failed for batch {summary_batch_id}: {e}")
                for job in jobs:
                    db.mark_rescan_batch_job_error(job["shortcode"], str(e))

        by_scoring_pair = defaultdict(list)
        for job in db.get_rescan_batch_jobs(phase="scoring_pending"):
            by_scoring_pair[(job["importance_batch_id"], job["embedding_batch_id"])].append(job)

        for (importance_batch_id, embedding_batch_id), jobs in by_scoring_pair.items():
            try:
                done, waiting = _finalize_scoring_group(db, importance_batch_id, embedding_batch_id, jobs)
                finalized.extend(done)
                still_waiting.extend(waiting)
            except Exception as e:
                print(f"⚠️  [rescan-batch] scoring-phase check failed for pair "
                      f"({importance_batch_id}, {embedding_batch_id}): {e}")
                for job in jobs:
                    db.mark_rescan_batch_job_error(job["shortcode"], str(e))

        return {
            "summary_advanced": summary_advanced,
            "summary_failed": summary_failed,
            "finalized": finalized,
            "still_waiting": still_waiting,
        }
    finally:
        _lock.release()


def _fail_job(db, shortcode: str, reason: str):
    print(f"❌ [rescan-batch] {shortcode}: {reason} — leaving the existing post untouched.")
    db.delete_rescan_batch_job(shortcode)


def _advance_summary_group(db, summary_batch_id: str, jobs: list):
    router = get_router()
    status = router.get_batch_status(summary_batch_id)
    batch_status = status.get("status")

    if batch_status in _TERMINAL_BAD:
        for job in jobs:
            _fail_job(db, job["shortcode"], f"shared summary batch {batch_status}")
        return [], [j["shortcode"] for j in jobs], []

    if batch_status not in _TERMINAL_OK:
        return [], [], [j["shortcode"] for j in jobs]

    results = router.get_batch_results(summary_batch_id)
    results_by_id = {r.get("custom_id"): r for r in results}

    resolved = []  # (job, title, summary, tags, music, category, language)
    advanced, failed = [], []
    for job in jobs:
        shortcode = job["shortcode"]
        row = results_by_id.get(shortcode)
        summary_text = router.extract_batch_chat_text(row) if row else None
        if not summary_text:
            _fail_job(db, shortcode, "no usable result in shared summary batch (expired/errored request)")
            failed.append(shortcode)
            continue
        state = json.loads(job["state_json"] or "{}")
        title, summary, tags, music, category, language = parse_summary(summary_text)
        # Always prefer the pre-resolved music (Shazam output if audio was
        # redone, otherwise the post's already-stored value) over whatever
        # the LLM guessed in its own MUSIC field this time — same rule
        # apply_music_override() enforces in the immediate/first-analysis path.
        music = state.get("music") or music
        state.update({"title": title, "summary_text": summary, "tags": tags,
                       "music": music, "category": category, "language": language})
        resolved.append((job, state))

    if resolved:
        # Uses the router's OPENAI_TEXT_MODEL default, matching the immediate
        # pipeline's generate_importance_text() — importance scoring is pinned to
        # one specific model (rather than the latency-ranked order) so judgment
        # stays consistent across posts, not because it needs a different model
        # from everything else.
        importance_reqs = [
            router.build_batch_chat_request(
                job["shortcode"],
                build_importance_prompt(state["title"], state["summary_text"], state["tags"], state["category"]),
            ) for job, state in resolved
        ]
        embedding_reqs = [
            router.build_batch_embedding_request(
                job["shortcode"],
                f"{state['title']}\n\n{state['summary_text']}\n\nTags: {', '.join(state['tags'])}",
            ) for job, state in resolved
        ]
        importance_batch_id = router.submit_openai_batch(importance_reqs, endpoint="/v1/chat/completions")
        embedding_batch_id = router.submit_openai_batch(embedding_reqs, endpoint="/v1/embeddings")
        for job, state in resolved:
            db.advance_rescan_batch_job(
                job["shortcode"], phase="scoring_pending",
                importance_batch_id=importance_batch_id, embedding_batch_id=embedding_batch_id,
                state_json=json.dumps(state),
            )
            advanced.append(job["shortcode"])
        print(f"📦 [rescan-batch] {len(resolved)} shortcode(s) resolved from shared summary batch "
              f"{summary_batch_id} -> shared importance batch {importance_batch_id}, "
              f"shared embedding batch {embedding_batch_id}")

    return advanced, failed, []


def _finalize_scoring_group(db, importance_batch_id: str, embedding_batch_id: str, jobs: list):
    router = get_router()
    importance_status = router.get_batch_status(importance_batch_id)
    embedding_status = router.get_batch_status(embedding_batch_id)
    if importance_status.get("status") not in _TERMINAL or embedding_status.get("status") not in _TERMINAL:
        return [], [j["shortcode"] for j in jobs]

    importance_results = {}
    if importance_status.get("status") in _TERMINAL_OK:
        for r in router.get_batch_results(importance_batch_id):
            importance_results[r.get("custom_id")] = r

    embedding_results = {}
    if embedding_status.get("status") in _TERMINAL_OK:
        for r in router.get_batch_results(embedding_batch_id):
            embedding_results[r.get("custom_id")] = r

    finalized = []
    for job in jobs:
        shortcode = job["shortcode"]
        state = json.loads(job["state_json"] or "{}")

        importance = None
        row = importance_results.get(shortcode)
        if row:
            raw = router.extract_batch_chat_text(row)
            if raw:
                importance = parse_importance(raw)
        importance = apply_trusted_creator_boost(importance, state.get("username", ""))

        embedding = None
        row = embedding_results.get(shortcode)
        if row:
            embedding = router.extract_batch_embedding(row)

        saved = db.save_analysis(
            shortcode=shortcode, url=job["url"], username=state.get("username", ""),
            title=state.get("title", ""), summary=state.get("summary_text", ""),
            tags=state.get("tags", []), music=state.get("music", ""),
            category=state.get("category", []), language=state.get("language", []),
            importance=importance, media_files=state.get("media_files", []),
            visual_analysis=state.get("visual_text", ""), audio_transcription=state.get("audio_text", ""),
            text_analysis=state.get("text_text", ""), likes=state.get("likes", 0),
            post_date=state.get("post_date"), content_type=job.get("content_type") or "instagram",
            thumbnail=state.get("thumbnail", ""), source_hashtags=state.get("source_hashtags"),
            embedding=embedding, model_used="openai_gpt41_batch",
            transcription_backend=state.get("transcription_backend", ""), caption=state.get("caption", ""),
        )
        if not saved:
            print(f"❌ [rescan-batch] {shortcode}: save_analysis failed — leaving job in place, will retry on next check")
            continue
        db.delete_rescan_batch_job(shortcode)
        print(f"✓ [rescan-batch] {shortcode}: finalized")
        finalized.append(shortcode)

    return finalized, []
