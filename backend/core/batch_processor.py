#!/usr/bin/env python3
"""
Resumption logic for ANALYSIS_MODE=batch (see main.py). main.py runs as a
subprocess and exits immediately after submitting an OpenAI Batch API job —
there's no live process left to resume once that job completes, so this
module is what actually finishes the pipeline once OpenAI's batch results
are ready. Called in-process from api.py: once on backend startup, and on
demand via POST /batches/check (the "Check batches" button in
superbrain-web). Deliberately no periodic polling — batch turnaround can be
minutes to 24h, and this app runs on a laptop that isn't always on.

Deliberately does NOT import main.py — api.py never imports main.py (see
backend/CLAUDE.md's subprocess-decoupling note: main.py always runs as a
spawned subprocess so a crash/hang there can't take down the API process).
The pure parsing/prompt-building logic this needs (parse_summary,
apply_music_override, build_final_summary_prompt) lives in
core/summary_parser.py specifically so both main.py and this module can
share it without crossing that boundary.

Three-phase lifecycle per shortcode (see batch_jobs table in core/database.py):
  analysis_pending — one bundled batch job (one vision request per video/
                      image file, plus one text-analysis request) submitted,
                      not yet resolved. This is the normal entry point —
                      visual/text analysis moved to batch mode too, not just
                      the summary, since both are normally OpenAI calls at
                      full synchronous price. (Skipped for the rare reel with
                      no media/info.txt at all — main.py submits straight to
                      summary_pending for those.)
  summary_pending  — combined-summary batch submitted, not yet resolved.
  scoring_pending  — summary resolved; importance + embedding batches
                      submitted concurrently (two sub-batches, since OpenAI
                      batch jobs are single-endpoint: one chat-completions
                      job for importance, one embeddings job).
"""

import json
import threading

from core.database import get_db
from core.model_router import get_router
from core.importance import build_importance_prompt, parse_importance, apply_trusted_creator_boost
from core.summary_parser import parse_summary, apply_music_override, build_final_summary_prompt

_lock = threading.Lock()

_TERMINAL_OK = {"completed"}
_TERMINAL_BAD = {"failed", "expired", "cancelled"}
_TERMINAL = _TERMINAL_OK | _TERMINAL_BAD


def check_and_advance_batches() -> dict:
    """
    Sweep every in-flight batch_jobs row and advance whatever has completed.
    Not periodic — called once on backend startup and on demand via
    POST /batches/check. A no-op (fast) when nothing is pending. Guarded by
    a module-level lock so an overlapping startup-check and manual-check
    can't double-submit phase-2 batches for the same item.
    """
    if not _lock.acquire(blocking=False):
        return {"skipped": "a batch check is already running"}
    try:
        db = get_db()
        analysis_advanced, analysis_failed = [], []
        summary_advanced, summary_failed = [], []
        finalized, still_waiting = [], []

        for job in db.get_batch_jobs(phase="analysis_pending"):
            shortcode = job["shortcode"]
            try:
                if _advance_analysis_phase(db, job):
                    analysis_advanced.append(shortcode)
                else:
                    still_waiting.append(shortcode)
            except Exception as e:
                print(f"⚠️  [batch] analysis-phase check failed for {shortcode}: {e}")
                db.mark_batch_job_error(shortcode, str(e))
                analysis_failed.append(shortcode)

        for job in db.get_batch_jobs(phase="summary_pending"):
            shortcode = job["shortcode"]
            try:
                if _advance_summary_phase(db, job):
                    summary_advanced.append(shortcode)
                else:
                    still_waiting.append(shortcode)
            except Exception as e:
                print(f"⚠️  [batch] summary-phase check failed for {shortcode}: {e}")
                db.mark_batch_job_error(shortcode, str(e))
                summary_failed.append(shortcode)

        for job in db.get_batch_jobs(phase="scoring_pending"):
            shortcode = job["shortcode"]
            try:
                if _finalize_scoring_phase(db, job):
                    finalized.append(shortcode)
                else:
                    still_waiting.append(shortcode)
            except Exception as e:
                print(f"⚠️  [batch] scoring-phase check failed for {shortcode}: {e}")
                db.mark_batch_job_error(shortcode, str(e))

        return {
            "analysis_advanced": analysis_advanced,
            "analysis_failed": analysis_failed,
            "summary_advanced": summary_advanced,
            "summary_failed": summary_failed,
            "finalized": finalized,
            "still_waiting": still_waiting,
        }
    finally:
        _lock.release()


def _advance_analysis_phase(db, job: dict) -> bool:
    """Check one analysis_pending job (bundled vision + text batch).
    Returns True if it advanced to summary_pending (or was resolved as a
    failure), False if still waiting on OpenAI."""
    shortcode = job["shortcode"]
    router = get_router()
    status = router.get_batch_status(job["analysis_batch_id"])
    batch_status = status.get("status")

    if batch_status in _TERMINAL_BAD:
        print(f"❌ [batch] analysis batch {batch_status} for {shortcode} — queuing for retry")
        db.queue_for_retry(shortcode, job["url"], job.get("content_type") or "instagram",
                            "batch_analysis_failed", retry_hours=6)
        db.delete_batch_job(shortcode)
        return True

    if batch_status not in _TERMINAL_OK:
        return False  # still validating/in_progress/finalizing

    raw_results = router.get_batch_results(job["analysis_batch_id"])
    by_id = {r.get("custom_id"): r for r in raw_results}
    state = json.loads(job["state_json"] or "{}")
    visual_files = state.get("visual_files", [])

    visual_texts = []
    visual_entries = []
    for i, meta in enumerate(visual_files):
        row = by_id.get(f"visual__{i}")
        text = router.extract_batch_chat_text(row) if row else None
        if text:
            visual_texts.append(text)
            visual_entries.append({
                "file": meta.get("file", ""),
                "type": meta.get("type", "video"),
                "output": f"📝 ANALYSIS:\n{'-' * 70}\n{text}\n{'-' * 70}",
            })

    text_text = ""
    text_entries = []
    if state.get("text_file"):
        row = by_id.get("text")
        text = router.extract_batch_chat_text(row) if row else None
        if text:
            text_text = text
            text_entries.append({
                "file": state["text_file"],
                "output": f"🔍 ANALYSIS:\n{'-' * 70}\n{text}\n{'-' * 70}",
            })

    audio_entries = []
    if state.get("audio_text"):
        audio_entries.append({
            "file": "",
            "output": f"📝 TRANSCRIBED TEXT:\n{'-' * 70}\n{state['audio_text']}\n{'-' * 70}",
        })

    results = {
        "visual": visual_entries,
        "audio_transcription": audio_entries,
        "music_identification": state.get("music_identification", []),
        "text": text_entries,
    }
    prompt = build_final_summary_prompt(
        results, job["url"], state.get("source_caption", ""), state.get("source_hashtags")
    )
    summary_req = router.build_batch_chat_request(shortcode, prompt)
    summary_batch_id = router.submit_openai_batch([summary_req], endpoint="/v1/chat/completions")

    # Collapse into the same flattened strings the "nothing to analyze"
    # fallback path (main.py) stores directly — _finalize_scoring_phase()
    # reads these regardless of which path produced them.
    state["visual_text"] = "\n\n".join(visual_texts)
    state["text_text"] = text_text

    db.advance_batch_job(shortcode, phase="summary_pending",
                          summary_batch_id=summary_batch_id, state_json=json.dumps(state))
    print(f"📦 [batch] {shortcode}: visual+text analysis resolved, submitted summary batch")
    return True


def _advance_summary_phase(db, job: dict) -> bool:
    """Check one summary_pending job. Returns True if it advanced to
    scoring_pending (or was resolved as a failure), False if still waiting
    on OpenAI."""
    shortcode = job["shortcode"]
    router = get_router()
    status = router.get_batch_status(job["summary_batch_id"])
    batch_status = status.get("status")

    if batch_status in _TERMINAL_BAD:
        print(f"❌ [batch] summary batch {batch_status} for {shortcode} — queuing for retry")
        db.queue_for_retry(shortcode, job["url"], job.get("content_type") or "instagram",
                            "batch_summary_failed", retry_hours=6)
        db.delete_batch_job(shortcode)
        return True

    if batch_status not in _TERMINAL_OK:
        return False  # still validating/in_progress/finalizing

    results = router.get_batch_results(job["summary_batch_id"])
    row = next((r for r in results if r.get("custom_id") == shortcode), None)
    summary_text = router.extract_batch_chat_text(row) if row else None
    if not summary_text:
        print(f"❌ [batch] summary batch completed but no usable result for {shortcode} — queuing for retry")
        db.queue_for_retry(shortcode, job["url"], job.get("content_type") or "instagram",
                            "batch_summary_empty", retry_hours=6)
        db.delete_batch_job(shortcode)
        return True

    state = json.loads(job["state_json"] or "{}")
    title, summary, tags, music, category, language = parse_summary(summary_text)
    music = apply_music_override(music, state.get("music_identification"))

    importance_prompt = build_importance_prompt(title, summary, tags, category)
    embedding_text = f"{title}\n\n{summary}\n\nTags: {', '.join(tags)}"

    # Uses the router's OPENAI_TEXT_MODEL default, matching the immediate
    # pipeline's generate_importance_text() — importance scoring is pinned to
    # one specific model (rather than the latency-ranked order) so judgment
    # stays consistent across posts, not because it needs a different model
    # from everything else.
    importance_req = router.build_batch_chat_request(shortcode, importance_prompt)
    embedding_req = router.build_batch_embedding_request(shortcode, embedding_text)
    importance_batch_id = router.submit_openai_batch([importance_req], endpoint="/v1/chat/completions")
    embedding_batch_id = router.submit_openai_batch([embedding_req], endpoint="/v1/embeddings")

    state.update({
        "title": title, "summary_text": summary, "tags": tags,
        "music": music, "category": category, "language": language,
    })
    db.advance_batch_job(
        shortcode, phase="scoring_pending",
        importance_batch_id=importance_batch_id,
        embedding_batch_id=embedding_batch_id,
        state_json=json.dumps(state),
    )
    print(f"📦 [batch] {shortcode}: summary resolved, submitted importance+embedding batches")
    return True


def _finalize_scoring_phase(db, job: dict) -> bool:
    """Check one scoring_pending job (importance + embedding sub-batches).
    Only finalizes once BOTH are terminal — a failed sub-batch degrades
    gracefully to None (importance/embedding are best-effort in the
    immediate pipeline too). Returns True if finalized, False if still
    waiting on either sub-batch."""
    shortcode = job["shortcode"]
    router = get_router()

    importance_status = router.get_batch_status(job["importance_batch_id"])
    embedding_status = router.get_batch_status(job["embedding_batch_id"])
    if importance_status.get("status") not in _TERMINAL or embedding_status.get("status") not in _TERMINAL:
        return False

    state = json.loads(job["state_json"] or "{}")

    importance = None
    if importance_status.get("status") in _TERMINAL_OK:
        results = router.get_batch_results(job["importance_batch_id"])
        row = next((r for r in results if r.get("custom_id") == shortcode), None)
        raw = router.extract_batch_chat_text(row) if row else None
        if raw:
            importance = parse_importance(raw)
    importance = apply_trusted_creator_boost(importance, state.get("username", ""))

    embedding = None
    if embedding_status.get("status") in _TERMINAL_OK:
        results = router.get_batch_results(job["embedding_batch_id"])
        row = next((r for r in results if r.get("custom_id") == shortcode), None)
        embedding = router.extract_batch_embedding(row) if row else None

    saved = db.save_analysis(
        shortcode=shortcode,
        url=job["url"],
        username=state.get("username", ""),
        title=state.get("title", ""),
        summary=state.get("summary_text", ""),
        tags=state.get("tags", []),
        music=state.get("music", ""),
        category=state.get("category", []),
        language=state.get("language", []),
        importance=importance,
        media_files=state.get("media_files", []),
        visual_analysis=state.get("visual_text", ""),
        audio_transcription=state.get("audio_text", ""),
        text_analysis=state.get("text_text", ""),
        likes=state.get("likes", 0),
        post_date=state.get("post_date"),
        content_type=job.get("content_type") or "instagram",
        thumbnail=state.get("thumbnail", ""),
        source_hashtags=state.get("source_hashtags"),
        embedding=embedding,
        model_used="openai_gpt41_batch",
        transcription_backend=state.get("transcription_backend", ""),
        caption=state.get("caption", ""),
        date_saved=state.get("date_saved"),
    )

    if not saved:
        print(f"❌ [batch] {shortcode}: save_analysis failed — leaving batch job in place, will retry on next check")
        return False

    db.delete_batch_job(shortcode)
    db.remove_from_queue(shortcode)
    print(f"✓ [batch] {shortcode}: finalized")
    return True
