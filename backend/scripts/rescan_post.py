#!/usr/bin/env python3
"""
Rescan an existing, already-analyzed post to fix a version/prompt gap — the
single script that toggles between single-reel and whole-version modes (see
backend/CLAUDE.md's "Rescan pipeline" section for the full picture).

Deliberately separate from main.py / core/batch_processor.py (first-time
analysis) — never imports either, never modifies them, and never deletes an
existing row: every write goes through db.save_analysis()'s existing upsert,
so a rescan that fails partway always leaves the original row untouched.

Usage:
    python scripts/rescan_post.py <shortcode>              # single reel, always synchronous
    python scripts/rescan_post.py --batch <sc1,sc2,...>    # whole cohort — see run_batch()

Exit codes: 0 = done (saved, or nothing needed doing), 1 = hard failure,
2 = temporarily retryable (rate-limited) — row untouched either way.
"""

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _load_env_file():
    """Load backend/.env into the process environment, if present — see the
    identical helper in main.py/api.py for the full rationale (not imported
    from either, per the no-cross-import constraint; this is ~15 lines)."""
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

from core.database import get_db
from core.rescan_plan import decide_rescan_plan
from core.importance import (
    build_importance_prompt, parse_importance, parse_importance_reason, apply_trusted_creator_boost,
    score_and_stamp_importance,
)
from core.summary_parser import parse_summary, apply_music_override
from core.categories import category_prompt
from core.languages import language_prompt
from core.media_store import MEDIA_DIR, relocate_to_media_store
from instagram.instagram_downloader import (
    download_instagram_content, extract_audio_from_video, RetryableDownloadError,
)
from analyzers.youtube_analyzer import analyze_youtube
from analyzers.webpage_analyzer import analyze_webpage

RETRYABLE = "__RETRYABLE__"

# Bounded concurrency for the common case — a post whose local media is
# already downloaded never touches Instagram during a rescan, so there's no
# ban-risk reason to process those sequentially the way first-time analysis
# must (max_concurrent=1 in api.py, to protect the Instagram account from
# concurrent-download traffic). Mirrors main.py's own
# ThreadPoolExecutor(max_workers=3) precedent for its light-tasks phase —
# just applied across reels here instead of within one. The rare post that
# genuinely needs a real Instagram redownload is deliberately excluded from
# this pool and processed sequentially instead (see _classify_for_dispatch).
LOCAL_RESOLUTION_CONCURRENCY = int(os.getenv("RESCAN_LOCAL_CONCURRENCY", "4"))

# ANALYSIS_MODE=batch: submit the shared OpenAI batch in chunks of this size
# as soon as each chunk's local resolution is done, instead of waiting for
# an entire large cohort to finish before submitting anything. Without
# chunking, a 100+-reel rescan has zero durable checkpoint (nothing written
# to rescan_batch_jobs, nothing safe from a backend restart) until the very
# last reel's local analysis completes — chunking means a batch becomes
# durable every N resolved reels.
OPENAI_BATCH_CHUNK_SIZE = int(os.getenv("RESCAN_BATCH_CHUNK_SIZE", "15"))


# ── Small local duplicates of main.py's generic helpers ─────────────────────
# (not imported — see module docstring)

def run_script(script_name, args):
    cmd = [sys.executable, str(BACKEND_DIR / script_name)] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", env=env)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def _extract_section(output: str, marker: str) -> str:
    if marker not in output:
        return output[:2000]
    after = output.split(marker, 1)[1]
    content_lines, started = [], False
    for line in after.split("\n"):
        stripped = line.strip("-").strip("=").strip("─").strip()
        if not started:
            if stripped:
                started = True
                content_lines.append(line)
        else:
            raw = line.strip()
            if raw.startswith(("─────", "-----", "=====", "*****")):
                break
            content_lines.append(line)
    return "\n".join(content_lines).strip()


def _clean_visual(output: str) -> str:
    return _extract_section(output, "📝 ANALYSIS:")


def _clean_audio(output: str) -> str:
    return _extract_section(output, "📝 TRANSCRIBED TEXT:")


def _clean_text(output: str) -> str:
    return _extract_section(output, "🔍 ANALYSIS:")


def _audio_backend(output: str) -> str:
    m = re.search(r"🔧 Backend:\s*(.+)", output)
    return m.group(1).strip() if m else ""


# ── Prompt builder — takes pre-cleaned text blocks, not raw per-file results ─
# (main.py's build_final_summary_prompt() expects raw analyzer stdout with
# section markers; a skipped step here only has already-clean stored text to
# offer, so this is a deliberate small duplicate with the same template,
# adapted to accept clean blocks uniformly whether freshly produced or reused.)

def build_rescan_prompt(visual_text: str, audio_text: str, music_text: str, text_text: str,
                         url: str, caption: str = "", hashtags=None) -> str:
    visual_summary = f"VISUAL ANALYSIS:\n- {visual_text[:3000]}\n" if visual_text else ""
    audio_summary = f"AUDIO TRANSCRIPTION:\n- {audio_text[:3000]}\n" if audio_text else ""
    music_info = f"MUSIC:\n- {music_text}\n" if music_text else ""
    text_summary = f"TEXT ANALYSIS:\n{text_text[:2000]}\n" if text_text else ""

    caption_block = ""
    if caption and caption.strip():
        caption_block = f"ORIGINAL POST CAPTION (unverified — may be irrelevant or spam, see instructions below):\n{caption.strip()}\n"
    hashtags_block = ""
    if hashtags:
        hashtags_block = f"ORIGINAL POST HASHTAGS: {' '.join('#' + h.lstrip('#') for h in hashtags)}\n"

    combined_info = f"""
INSTAGRAM POST: {url}

{caption_block}
{hashtags_block}

{visual_summary}

{audio_summary}

{music_info}

{text_summary}
"""

    return f"""Based on the following analysis of an Instagram post, create a detailed structured summary that preserves every concrete, useful detail found below — not just a thematic overview.

{combined_info}

BEFORE YOU WRITE ANYTHING: compare the ORIGINAL POST CAPTION/HASHTAGS above to the VISUAL ANALYSIS / AUDIO TRANSCRIPTION / TEXT ANALYSIS above, and classify the relationship into exactly one of these three cases:

1. CONSISTENT — the caption describes, adds detail to, or is simply narrower/broader than what the media shows (e.g. a 10-second clip of a finished dish while the caption gives the full recipe; a short personal clip with a caption telling the actual story; generic/ambient b-roll — walking, a talking-head, a plain product shot, a static single image — paired with a caption that supplies the real substance). This is extremely common and completely legitimate: plenty of real posts put the actual information in the text and use the video only as illustration or a hook, especially on short clips. Thin, generic, or non-specific media is NOT a sign of mismatch — it's normal, and the caption should be trusted and used normally.
2. GENUINE MISMATCH — the media itself shows a different, specific, self-contained subject that competes with and contradicts the caption: e.g. a screenshot of a different, identifiable social media post/account, a named person/place/event/object visibly different from what the caption claims, or on-screen text/speech that is clearly about an unrelated topic. The key test is not "does the media lack detail the caption has" — it's "does the media affirmatively show something else specific." This is a known spam pattern (pairing a caption about a trending topic with an unrelated 'hook' video to farm reach) but it is the exception, not the default assumption.
3. UNCLEAR — the media analysis is too thin/generic to tell either way. Treat this the same as CONSISTENT (trust the caption) — do not treat ambiguity as evidence of a mismatch.

Only for case 2 (GENUINE MISMATCH): build the TITLE, SUMMARY, and TAGS from what the visual/audio/text analysis actually shows, not from the caption, and add one short line at the end of the SUMMARY noting the mismatch plainly, e.g. "Note: this post's caption describes [caption topic], but the video/image itself actually shows [actual content] — caption and media do not match, likely mismatched/bait content." For cases 1 and 3, use the caption normally as you would for any post — do not add a mismatch note or second-guess a caption just because the video accompanying it is short, generic, or low on independently-verifiable detail.

Generate a report in this EXACT format:

📌 TITLE:
[Create a clear, descriptive title. Use the caption normally unless the classification above is GENUINE MISMATCH, in which case title this from what the media actually shows instead.]

📝 SUMMARY:
[A detailed summary — as long as it needs to be to capture the real content, not capped at a fixed sentence count. Include:
- Main content/theme
- Every specific, concrete detail found in the analysis above: exact ingredients/quantities, step-by-step instructions in order, specific locations/names/prices, tool/product names, numbers, measurements, links. Reproduce these specifics directly — do not paraphrase them away into vague generalities like "key ingredients" or "several steps."
- If this is a tutorial, recipe, itinerary, or how-to, list out the actual steps/items found in the analysis above, in order, not just a description that steps exist.
- Important highlights
- Any actionable items or recommendations
Only include details that are actually present in the analysis above — do not invent or guess specifics that weren't captured by the visual/audio analysis. If the analysis above is thin (e.g. no clear speech was transcribed and no on-screen text was found), say so plainly rather than padding the summary with generic filler.
Do not mention the absence of structural elements that were never expected in the first place — e.g. don't say "no instructions were given" or "no steps are provided" for a meme, joke, photo, quote, or other content that isn't a tutorial/recipe/how-to. Only note what's missing when its absence is actually notable (e.g. a recipe video with no visible ingredient list). Never write a sentence whose only purpose is to point out that something isn't present.

Apply the classification from above: for CONSISTENT or UNCLEAR, use the caption normally, including as the primary source of detail when the media itself is thin (a short clip, a single generic shot) — that's a normal post, not a gap to flag. Only for GENUINE MISMATCH, describe what the visual/audio/text analysis actually shows and include the one-line mismatch note described above instead of the caption's claims.]

🏷️ TAGS:
[Generate 8-12 relevant hashtags/keywords. Use the caption's topic normally unless the classification above is GENUINE MISMATCH, in which case tag what the media actually shows instead.]

🎵 MUSIC:
[Music/song name if found, or "No background music" or "Voiceover only"]

📂 CATEGORY:
{category_prompt()}

🌐 LANGUAGE:
{language_prompt()}

Be specific and thorough — prioritize capturing concrete, actionable detail over brevity."""


# ── Per-post local resolution ────────────────────────────────────────────────

def resolve_rescan_inputs(row: dict, plan) -> dict | str | None:
    """Resolve everything a rescan needs for one post, doing only the local
    work the plan calls for. Returns a state dict on success, RETRYABLE if a
    real redownload hit a transient Instagram error, or None on a permanent
    failure — callers must leave the row untouched in both non-success cases."""
    shortcode = row["shortcode"]
    media_dir = MEDIA_DIR / shortcode

    if plan.needs_redownload:
        print(f"  ⬇ [{shortcode}] No usable local media — downloading from Instagram...")
        try:
            download_folder = download_instagram_content(row["url"])
        except RetryableDownloadError as e:
            print(f"  ⏰ [{shortcode}] Retryable download error: {e}")
            return RETRYABLE
        except Exception as e:
            print(f"  ❌ [{shortcode}] Download error: {e}")
            return None
        if download_folder is None:
            print(f"  ❌ [{shortcode}] Download failed (post likely gone/private/blocked) — row left untouched.")
            return None
        relocate_to_media_store(download_folder, shortcode)

    mp4_files = sorted(media_dir.glob("*.mp4")) if media_dir.is_dir() else []
    jpg_files = sorted(media_dir.glob("*.jpg")) if media_dir.is_dir() else []
    mp3_files = sorted(media_dir.glob("*audio.mp3")) if media_dir.is_dir() else []
    info_file = media_dir / "info.txt" if (media_dir / "info.txt").exists() else None

    state = {
        "visual_text": row.get("visual_analysis") or "",
        "audio_text": row.get("audio_transcription") or "",
        "text_text": row.get("text_analysis") or "",
        "music": row.get("music") or "",
        "music_text": row.get("music") or "",
        "transcription_backend": row.get("transcription_backend") or "",
        "media_files": row.get("media_files") or [],
        "caption": row.get("caption") or "",
        "source_hashtags": row.get("source_hashtags") or [],
        "username": row.get("username") or "",
        "likes": row.get("likes") or 0,
        "post_date": row.get("post_date"),
        "thumbnail": row.get("thumbnail") or "",
    }

    if plan.redo_visual:
        print(f"  🎬 [{shortcode}] Re-running visual analysis ({len(mp4_files) + len(jpg_files)} file(s))...")
        visual_chunks = []
        for f in mp4_files + jpg_files:
            ok, stdout, _ = run_script("analyzers/visual_analyze.py", [str(f)])
            if ok:
                visual_chunks.append(_clean_visual(stdout))
        state["visual_text"] = "\n\n".join(c for c in visual_chunks if c)
        print(f"  ✓ [{shortcode}] Visual analysis done.")

    if plan.redo_audio:
        print(f"  🎙️  [{shortcode}] Re-running audio transcription...")
        audio_path = mp3_files[0] if mp3_files else None
        scratch_audio = None
        if audio_path is None and mp4_files:
            scratch_audio = media_dir / "audio.mp3"
            if extract_audio_from_video(str(mp4_files[0]), str(scratch_audio)):
                audio_path = scratch_audio
                state["media_files"] = list(set(state["media_files"]) | {"audio.mp3"})
        if audio_path is not None:
            ok, stdout, _ = run_script("analyzers/audio_transcribe.py", [str(audio_path)])
            if ok:
                state["audio_text"] = _clean_audio(stdout)
                state["transcription_backend"] = _audio_backend(stdout)
            ok, stdout, _ = run_script("analyzers/music_identifier.py", [str(audio_path)])
            state["music_text"] = stdout if ok else state["music_text"]
            state["music"] = apply_music_override(state["music"], [{"output": stdout}] if ok else [])
            print(f"  ✓ [{shortcode}] Audio transcription + music ID done.")

    if info_file:
        try:
            content = info_file.read_text(encoding="utf-8")
            m = re.search(r"Username: @(\S+)", content)
            if m:
                state["username"] = m.group(1)
            m = re.search(r"Likes: (\d+)", content)
            if m:
                state["likes"] = int(m.group(1))
            m = re.search(r"Date: ([\d\-: ]+)", content)
            if m:
                state["post_date"] = m.group(1)
            m = re.search(r"Caption:\n-+\n(.*?)\n-+\n", content, re.DOTALL)
            if m:
                caption_text = m.group(1).strip()
                state["caption"] = "" if caption_text == "No caption" else caption_text
        except Exception:
            pass

    return state


# ── Cheap path / summary+importance+embedding, shared by sync & immediate-batch ─

def _rescan_instagram_sync(db, row: dict) -> int:
    shortcode = row["shortcode"]
    plan = decide_rescan_plan(row)

    if plan.cheap_importance_only:
        print(f"  💸 [{shortcode}] Cheap path — importance rescore only.")
        importance = score_and_stamp_importance(
            db, shortcode, row.get("title"), row.get("summary"),
            row.get("tags"), row.get("category"), row.get("username"),
        )
        return 0 if importance is not None else 1

    print(f"  🔍 [{shortcode}] Plan: {', '.join(plan.reasons) or 'summary/category/importance rebuild only'}")
    state = resolve_rescan_inputs(row, plan)
    if state == RETRYABLE:
        db.queue_for_retry(shortcode, row["url"], "instagram", "rescan_instagram_rate_limit", retry_hours=24)
        return 2
    if state is None:
        return 1

    from core.model_router import get_router
    router = get_router()

    prompt = build_rescan_prompt(
        state["visual_text"], state["audio_text"], state["music_text"], state["text_text"],
        row["url"], state["caption"], state["source_hashtags"],
    )
    try:
        summary_text = router.generate_text(prompt)
    except Exception as e:
        print(f"  ❌ [{shortcode}] Summary generation failed: {e}")
        return 1
    if not summary_text:
        print(f"  ❌ [{shortcode}] Empty summary response.")
        return 1

    title, summary, tags, music, category, language = parse_summary(summary_text)
    if not plan.redo_audio:
        music = state["music"]  # nothing fresh to override with

    importance_prompt = build_importance_prompt(title, summary, tags, category)
    try:
        importance_raw = router.generate_importance_text(importance_prompt)
    except Exception as e:
        print(f"  ⚠️  [{shortcode}] Importance scoring failed: {e}")
        importance_raw = None
    importance, importance_reason = apply_trusted_creator_boost(
        parse_importance(importance_raw) if importance_raw else None,
        state["username"],
        parse_importance_reason(importance_raw) if importance_raw else None,
    )

    embedding = None
    try:
        embedding = router.generate_embedding(f"{title}\n\n{summary}\n\nTags: {', '.join(tags)}")
    except Exception as e:
        print(f"  ⚠️  [{shortcode}] Embedding generation failed: {e}")

    saved = db.save_analysis(
        shortcode=shortcode, url=row["url"], username=state["username"],
        title=title, summary=summary, tags=tags, music=music, category=category,
        visual_analysis=state["visual_text"], audio_transcription=state["audio_text"],
        text_analysis=state["text_text"], likes=state["likes"], post_date=state["post_date"],
        content_type="instagram", thumbnail=state["thumbnail"],
        source_hashtags=state["source_hashtags"], embedding=embedding,
        language=language, media_files=state["media_files"], importance=importance,
        importance_reason=importance_reason,
        model_used=router.last_model_used, transcription_backend=state["transcription_backend"],
        caption=state["caption"],
    )
    return 0 if saved else 1


def _rescan_youtube_or_webpage_sync(db, row: dict) -> int:
    shortcode, url, content_type = row["shortcode"], row["url"], row["content_type"]
    result = analyze_youtube(url) if content_type == "youtube" else analyze_webpage(url)
    if result.get("error") or not result.get("raw_output"):
        print(f"  ❌ [{shortcode}] {content_type} re-analysis failed: {result.get('error') or 'empty response'}")
        return 1

    raw = result["raw_output"]
    title, summary, tags, music, category, language = parse_summary(raw)
    author = result.get("channel") or result.get("author") or ""

    from core.model_router import get_router
    router = get_router()
    importance_prompt = build_importance_prompt(title, summary, tags, category)
    try:
        importance_raw = router.generate_importance_text(importance_prompt)
    except Exception as e:
        print(f"  ⚠️  [{shortcode}] Importance scoring failed: {e}")
        importance_raw = None
    importance, importance_reason = apply_trusted_creator_boost(
        parse_importance(importance_raw) if importance_raw else None,
        author,
        parse_importance_reason(importance_raw) if importance_raw else None,
    )
    embedding = None
    try:
        embedding = router.generate_embedding(f"{title}\n\n{summary}\n\nTags: {', '.join(tags)}")
    except Exception as e:
        print(f"  ⚠️  [{shortcode}] Embedding generation failed: {e}")

    saved = db.save_analysis(
        shortcode=shortcode, url=url, username=author, title=title, summary=summary,
        tags=tags, music=music, category=category, language=language, importance=importance,
        importance_reason=importance_reason,
        visual_analysis="", audio_transcription="", text_analysis=raw,
        content_type=content_type, thumbnail=result.get("thumbnail", ""),
        embedding=embedding, post_date=result.get("post_date"),
    )
    return 0 if saved else 1


def run_single(shortcode: str) -> int:
    db = get_db()
    row = db.check_cache(shortcode)
    if not row:
        print(f"❌ [{shortcode}] Not found.")
        return 1
    db.mark_processing(shortcode, row.get("url"), row.get("content_type"))
    try:
        if row.get("content_type") in ("youtube", "webpage"):
            return _rescan_youtube_or_webpage_sync(db, row)
        return _rescan_instagram_sync(db, row)
    except Exception as e:
        # Never let an unexpected exception propagate out of a single
        # shortcode's rescan — this is also what --batch/ANALYSIS_MODE=immediate
        # relies on to keep processing the rest of a cohort after one post's
        # rescan blows up. The post's row is untouched either way (nothing
        # was written yet at the point any of these calls could raise).
        print(f"❌ [{shortcode}] Unexpected error during rescan: {e}")
        return 1
    finally:
        db.remove_from_queue(shortcode)


def _classify_for_dispatch(shortcodes: list, by_shortcode: dict):
    """Split shortcodes into (parallel_safe, needs_redownload, missing).
    Everything except a genuine Instagram redownload is safe to run
    concurrently — YouTube/webpage posts never touch Instagram at all, and
    an Instagram post whose local media is already present only makes AI
    provider calls during a rescan. Only needs_redownload actually hits
    Instagram, so only that group is kept serialized."""
    parallel_safe, needs_redownload, missing = [], [], []
    for sc in shortcodes:
        row = by_shortcode.get(sc)
        if row is None:
            missing.append(sc)
            continue
        if row.get("content_type") in ("youtube", "webpage"):
            parallel_safe.append((sc, row, None))
            continue
        plan = decide_rescan_plan(row)
        (needs_redownload if plan.needs_redownload else parallel_safe).append((sc, row, plan))
    return parallel_safe, needs_redownload, missing


def _resolve_one_for_batch_mode(db, sc: str, row: dict, plan):
    """ANALYSIS_MODE=batch, local-only resolution for one shortcode (no LLM
    summary call — that's deferred to the shared batch submission). Returns
    a (sc, row, plan, state) tuple to be batched, or None if nothing needs
    batching (cheap/YouTube/webpage/failed/retried — all fully handled here)."""
    if row.get("content_type") in ("youtube", "webpage"):
        db.mark_processing(sc, row.get("url"), row.get("content_type"))
        try:
            _rescan_youtube_or_webpage_sync(db, row)
        finally:
            db.remove_from_queue(sc)
        return None

    db.mark_processing(sc, row.get("url"), "instagram")
    try:
        if plan.cheap_importance_only:
            score_and_stamp_importance(
                db, sc, row.get("title"), row.get("summary"),
                row.get("tags"), row.get("category"), row.get("username"),
            )
            return None
        state = resolve_rescan_inputs(row, plan)
        if state == RETRYABLE:
            db.queue_for_retry(sc, row["url"], "instagram", "rescan_instagram_rate_limit", retry_hours=24)
            return None
        if state is None:
            return None
        return (sc, row, plan, state)
    except Exception as e:
        # One shortcode's unexpected failure while resolving local inputs
        # must not abort the whole cohort — skip it, leave its row
        # untouched, move on.
        print(f"❌ [{sc}] Unexpected error resolving local inputs: {e}")
        return None
    finally:
        db.remove_from_queue(sc)


def run_batch(shortcodes: list) -> int:
    """--batch mode: ANALYSIS_MODE=immediate runs the has-local-media cohort
    concurrently (bounded pool) and the needs-redownload cohort sequentially
    in this same process; ANALYSIS_MODE=batch does the same split for LOCAL
    resolution, then submits resolved shortcodes to OpenAI in chunks of
    OPENAI_BATCH_CHUNK_SIZE as they accumulate, rather than one giant batch
    at the very end. See LOCAL_RESOLUTION_CONCURRENCY / OPENAI_BATCH_CHUNK_SIZE
    above."""
    analysis_mode = os.getenv("ANALYSIS_MODE", "immediate").strip().lower()
    db = get_db()
    rows = db.get_posts_by_shortcodes(shortcodes)
    by_shortcode = {r["shortcode"]: r for r in rows}
    parallel_safe, needs_redownload, missing = _classify_for_dispatch(shortcodes, by_shortcode)
    for sc in missing:
        print(f"❌ [{sc}] Not found — skipping.")
    print(f"➡ {len(parallel_safe)} reel(s) have local media (parallel, up to "
          f"{LOCAL_RESOLUTION_CONCURRENCY} at once), {len(needs_redownload)} need a real "
          f"Instagram redownload (sequential).")

    if analysis_mode != "batch":
        with ThreadPoolExecutor(max_workers=LOCAL_RESOLUTION_CONCURRENCY) as executor:
            futures = {executor.submit(run_single, sc): sc for sc, _, _ in parallel_safe}
            # Runs in this thread while the pool above works through the
            # rest in the background — protects Instagram from concurrent
            # download traffic, same reasoning as first-time analysis.
            for sc, _, _ in needs_redownload:
                print(f"⬇ Rescanning {sc} (redownload needed)...")
                run_single(sc)
            for future in as_completed(futures):
                sc = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"❌ [{sc}] Unexpected error: {e}")
                else:
                    print(f"✓ [{sc}] done")
        return 0

    # ANALYSIS_MODE=batch ----------------------------------------------------
    from core.model_router import get_router
    router = get_router()

    chunk_buffer = []  # (sc, row, plan, state) awaiting submission

    def _submit_chunk(force: bool = False):
        while len(chunk_buffer) >= OPENAI_BATCH_CHUNK_SIZE or (chunk_buffer and force):
            chunk = chunk_buffer[:OPENAI_BATCH_CHUNK_SIZE]
            del chunk_buffer[:OPENAI_BATCH_CHUNK_SIZE]
            requests_list = [
                router.build_batch_chat_request(
                    sc, build_rescan_prompt(state["visual_text"], state["audio_text"],
                                             state["music_text"], state["text_text"],
                                             row["url"], state["caption"], state["source_hashtags"])
                ) for sc, row, plan, state in chunk
            ]
            summary_batch_id = router.submit_openai_batch(requests_list, endpoint="/v1/chat/completions")
            print(f"📦 Submitted {len(requests_list)} shortcode(s) as one shared OpenAI batch: {summary_batch_id}")
            for sc, row, plan, state in chunk:
                state["content_type"] = "instagram"
                db.enqueue_rescan_batch_job(sc, row["url"], "instagram", summary_batch_id, json.dumps(state))
            if not chunk_buffer:
                break

    with ThreadPoolExecutor(max_workers=LOCAL_RESOLUTION_CONCURRENCY) as executor:
        futures = {
            executor.submit(_resolve_one_for_batch_mode, db, sc, row, plan): sc
            for sc, row, plan in parallel_safe
        }

        for sc, row, plan in needs_redownload:
            resolved = _resolve_one_for_batch_mode(db, sc, row, plan)
            if resolved:
                chunk_buffer.append(resolved)
                print(f"  ✓ [{sc}] locally resolved — buffered ({len(chunk_buffer)}/{OPENAI_BATCH_CHUNK_SIZE})")
                _submit_chunk()

        for future in as_completed(futures):
            sc = futures[future]
            try:
                resolved = future.result()
            except Exception as e:
                print(f"❌ [{sc}] Unexpected error: {e}")
                resolved = None
            if resolved:
                chunk_buffer.append(resolved)
                print(f"  ✓ [{sc}] locally resolved — buffered ({len(chunk_buffer)}/{OPENAI_BATCH_CHUNK_SIZE})")
                _submit_chunk()

    _submit_chunk(force=True)  # flush whatever's left as a final, possibly smaller chunk
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: rescan_post.py <shortcode> | rescan_post.py --batch <sc1,sc2,...>")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("Usage: rescan_post.py --batch <sc1,sc2,...>")
            sys.exit(1)
        shortcodes = [s for s in sys.argv[2].split(",") if s]
        sys.exit(run_batch(shortcodes))
    else:
        sys.exit(run_single(sys.argv[1]))


if __name__ == "__main__":
    main()
