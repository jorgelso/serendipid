#!/usr/bin/env python3
"""
SuperBrain - Instagram Content Analyzer
Main orchestrator that coordinates all analysis scripts
With parallel processing for better performance
"""

import sys
import os
from pathlib import Path
import subprocess
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


def _load_env_file():
    """Load backend/.env into the process environment, if present. Real env
    vars always take precedence — this only fills in what's not already
    set, so it's a no-op for anyone not using a .env file. When main.py is
    spawned as a subprocess by api.py (the normal path), it already
    inherits api.py's environment, which has .env merged in at that point —
    this is a safety net for running `python main.py <url>` standalone.
    Must run before any local module is imported below, since some (e.g.
    core.database's DATABASE_PATH) read env vars at import time."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

# Import local modules
from core.link_checker import validate_link
from core.database import get_db
from core.importance import parse_importance, parse_importance_reason, apply_trusted_creator_boost, build_importance_prompt
from core.media_store import relocate_to_media_store
from core.summary_parser import (
    parse_summary, apply_music_override, build_final_summary_prompt,
    _clean_visual, _clean_audio, _clean_text,
)
from analyzers.youtube_analyzer import analyze_youtube
from analyzers.webpage_analyzer import analyze_webpage

# Sentinel returned by run_*_analysis when the item has been queued for retry
RETRY_SENTINEL = "__ENQUEUED_FOR_RETRY__"

# ANALYSIS_MODE=batch submits the combined-summary LLM call (and, once that
# resolves, importance scoring + embedding) to OpenAI's Batch API instead of
# calling them synchronously — roughly half the cost, in exchange for
# turnaround up to 24h. Only affects the Instagram pipeline in main() below;
# YouTube/webpage analysis are single-call pipelines and stay synchronous
# regardless. See core/batch_processor.py for the resumption logic.
ANALYSIS_MODE = os.getenv("ANALYSIS_MODE", "immediate").strip().lower()

# Exit code signaling "submitted to a batch job, not a success/failure/retry"
# — distinct from 0=success, 1=hard failure, 2=queued-for-retry. api.py must
# not treat this as a failure, and must not remove the processing_queue row
# (db.enqueue_batch_job() already set it to status='batch').
BATCH_EXIT_CODE = 3

# Keywords that indicate a retryable quota / rate-limit failure
_QUOTA_KEYWORDS = (
    "resource_exhausted", "quota", "rate_limit", "rate limit",
    "429", "too many requests", "daily limit", "free tier",
    "insufficient_quota", "ratelimit", "all gemini models exhausted",
)

def _is_quota_error(err: str) -> bool:
    """Return True when an error string looks like a recoverable quota / rate-limit."""
    low = err.lower()
    return any(k in low for k in _QUOTA_KEYWORDS)

def print_header(title):
    """Print section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def print_section(title):
    """Print subsection"""
    print(f"\n{'─' * 80}")
    print(f"  {title}")
    print('─' * 80 + "\n")

def generate_final_summary(results, instagram_url, source_caption="", source_hashtags=None):
    """Generate comprehensive summary using all analysis results via ModelRouter."""
    from core.model_router import get_router

    prompt = build_final_summary_prompt(results, instagram_url, source_caption, source_hashtags)

    try:
        print("🤖 Generating comprehensive summary with AI...")
        router = get_router()
        summary = router.generate_text(prompt)

        if not summary:
            summary = "Unable to generate comprehensive summary."

        return summary, router.last_model_used

    except Exception as e:
        return f"Error generating summary: {e}\n\nRaw data available in individual analysis sections above.", None


def score_importance(title, summary_text, tags, category, username):
    """
    Score a post's importance in its own dedicated LLM call, separate from
    the combined title/summary/tags/music/category/language prompt. A
    single-purpose prompt follows the rubric far more consistently than
    importance being the 7th field competing for attention in one big
    structured-summary prompt — and generate_importance_text() pins the
    model to GPT-5.6 Luna specifically rather than whatever the
    latency-ranked router hands back for that request, for the same
    consistency reason.

    Returns (importance, importance_reason) — the model's justification is
    mandatory (see IMPORTANCE_PROMPT) and stored alongside the score so a
    surprising rating can be checked against its own stated reasoning.
    """
    from core.model_router import get_router
    prompt = build_importance_prompt(title, summary_text, tags, category)
    try:
        response = get_router().generate_importance_text(prompt)
        importance = parse_importance(response) if response else None
        reason = parse_importance_reason(response) if response else None
    except Exception as e:
        print(f"⚠️  Importance scoring failed: {e}")
        importance = None
        reason = None
    return apply_trusted_creator_boost(importance, username, reason)


def parse_info_txt(info_files):
    """Extract username/likes/post_date/caption from the first info.txt file,
    if any. Pure — shared by both the immediate and ANALYSIS_MODE=batch paths."""
    info = {"username": "", "likes": 0, "post_date": None, "caption": ""}
    if not info_files:
        return info
    try:
        with open(info_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
            username_match = re.search(r'Username: @(\S+)', content)
            likes_match = re.search(r'Likes: (\d+)', content)
            date_match = re.search(r'Date: ([\d\-: ]+)', content)
            caption_match = re.search(r'Caption:\n-+\n(.*?)\n-+\n', content, re.DOTALL)

            if username_match:
                info["username"] = username_match.group(1)
            if likes_match:
                info["likes"] = int(likes_match.group(1))
            if date_match:
                info["post_date"] = date_match.group(1)
            if caption_match:
                caption_text = caption_match.group(1).strip()
                info["caption"] = "" if caption_text == "No caption" else caption_text
    except Exception:
        pass
    return info


def extract_instagram_thumbnail(jpg_files, mp4_files):
    """Extract a base64 data-URI thumbnail: first downloaded jpg, or the
    first frame of the first video via cv2. Pure (no DB/network I/O) —
    shared by both the immediate and ANALYSIS_MODE=batch paths."""
    if jpg_files:
        print(f"🖼️  Saving thumbnail from {jpg_files[0].name}...")
        return _jpg_to_thumbnail(jpg_files[0])
    if mp4_files:
        try:
            import cv2
            import base64
            cap = cv2.VideoCapture(str(mp4_files[0]))
            ret, frame = cap.read()
            cap.release()
            if ret:
                h, w = frame.shape[:2]
                new_w = 480
                new_h = int(h * new_w / w)
                frame = cv2.resize(frame, (new_w, new_h))
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    encoded = base64.b64encode(buf.tobytes()).decode()
                    print("🖼️  Saved first-frame thumbnail from video")
                    return f"data:image/jpeg;base64,{encoded}"
        except Exception as thumb_err:
            print(f"⚠️  Could not extract video thumbnail: {thumb_err}")
    return ""


def run_script(script_name, args):
    """Run a Python script and return success status"""
    try:
        # Use sys.executable to ensure same Python interpreter (virtual env)
        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), script_name)] + args
        
        # Force UTF-8 encoding for subprocess
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def run_analysis_task(task_name, script_name, file_path, task_type="light"):
    """
    Run a single analysis task (for parallel execution)
    
    Args:
        task_name: Display name (e.g., "Visual Analysis")
        script_name: Python script to run
        file_path: Path to file to analyze
        task_type: "heavy" or "light" (for scheduling)
    
    Returns:
        dict with task results
    """
    start_time = time.time()
    print(f"  ⚡ Starting {task_name}: {Path(file_path).name}")
    
    success, stdout, stderr = run_script(script_name, [str(file_path)])
    
    elapsed = time.time() - start_time
    
    result = {
        'task_name': task_name,
        'file': Path(file_path).name,
        'success': success,
        'output': stdout if success else '',
        'error': stderr if not success else '',
        'elapsed': elapsed,
        'type': task_type
    }
    
    if success:
        print(f"  ✓ Completed {task_name}: {Path(file_path).name} ({elapsed:.1f}s)")
    else:
        print(f"  ✗ Failed {task_name}: {Path(file_path).name}")
    
    return result

def _audio_backend(output: str) -> str:
    """Extract which backend actually produced the transcript, e.g. 'Groq
    Whisper API' or 'Local Whisper (base)' — printed by
    analyzers/audio_transcribe.py on success."""
    m = re.search(r'🔧 Backend:\s*(.+)', output)
    return m.group(1).strip() if m else ""


def _jpg_to_thumbnail(jpg_path) -> str:
    """
    Read a JPEG file and return it as a base64-encoded data URI.
    Downsizes to max 480 px wide using Pillow if available; otherwise
    raw base64 is used (larger but still works as <img src=...>).
    """
    try:
        from PIL import Image
        import io
        img = Image.open(jpg_path)
        img.thumbnail((1080, 1080), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
    except Exception:
        # Pillow not available or failed — use raw bytes
        with open(jpg_path, "rb") as f:
            data = f.read()
    import base64
    encoded = base64.b64encode(data).decode()
    return f"data:image/jpeg;base64,{encoded}"

# ─────────────────────────────────────────────────────────────────────────────
#  Non-Instagram analysis flows (no download/pipeline needed)
# ─────────────────────────────────────────────────────────────────────────────

_EMOJI_MAP = {
    "TITLE":    "📌",
    "CHANNEL":  "📢",
    "DATE":     "📅",
    "SUMMARY":  "📝",
    "TAGS":     "🏷️",
    "MUSIC":    "🎵",
    "CATEGORY": "📂",
    "LANGUAGE": "🌐",
}

def _sanitise_yt_raw(raw: str, post_date: str | None) -> str:
    """
    Normalise YouTube Gemini raw output:
      • Replace U+FFFD replacement chars that precede known section labels
        with the correct emoji (model sometimes outputs \ufffd instead of
        📢 or 📝 due to encoding/font issues in the API layer).
      • Re-attach 🏷️ when the model omitted it before TAGS:.
      • Substitute the real upload date for "Unknown" in the DATE field.
    """
    lines = raw.splitlines()
    fixed = []
    for line in lines:
        stripped = line.strip()
        # Replace \ufffd or missing emoji before a known section label
        m = re.match(r'^(\ufffd\s*|)(\*{0,2})([A-Z]+)(\*{0,2}):(.*)$', stripped)
        if m:
            prefix, pre_bold, label, post_bold, rest = m.groups()
            if label in _EMOJI_MAP:
                line = f"{_EMOJI_MAP[label]} {pre_bold}{label}{post_bold}:{rest}"
        # Insert missing 🏷️ before bare 'TAGS:' (no emoji at all)
        elif re.match(r'^TAGS\s*:', stripped, re.IGNORECASE):
            line = re.sub(r'^TAGS\s*:', '🏷️ TAGS:', stripped, flags=re.IGNORECASE)
        fixed.append(line)

    result = "\n".join(fixed)

    # Substitute actual upload date for 'Unknown'
    if post_date:
        result = re.sub(
            r'(📅\s*DATE\s*:)\s*Unknown',
            rf'\1 {post_date}',
            result,
            flags=re.IGNORECASE,
        )

    return result

def run_youtube_analysis(url: str, shortcode: str, db):
    """Single-call YouTube analysis via Gemini native video support."""
    print_section("🎬 YouTube Video Analysis")
    print(f"📹 Analyzing: {url}")
    print("   (Gemini will access the video directly — no download required)")

    result = analyze_youtube(url)

    if result.get('error'):
        err = result['error']
        if _is_quota_error(err):
            db.queue_for_retry(shortcode, url, 'youtube', 'gemini_quota', retry_hours=24)
            print("⏰ All Gemini models quota-exhausted — queued for retry in 24 hours.")
            return RETRY_SENTINEL
        print(f"❌ YouTube analysis failed: {err}")
        return

    raw = result.get('raw_output', '')
    if not raw:
        print("❌ Received empty response from Gemini.")
        return

    # Clean up encoding artefacts and patch in the real upload date
    raw = _sanitise_yt_raw(raw, result.get('post_date'))

    print_section("📋 RAW GEMINI OUTPUT")
    print(raw[:2000])

    title, summary_text, tags, music, category, language = parse_summary(raw)
    yt_channel = result.get('channel', '')
    importance, importance_reason = score_importance(title, summary_text, tags, category, yt_channel)

    # Use upload date scraped directly from YouTube page (always accurate)
    yt_post_date = result.get('post_date')

    print_section("💾 Saving to Database")
    db.save_analysis(
        shortcode=shortcode,
        url=url,
        username=yt_channel,
        title=title,
        summary=summary_text,
        tags=tags,
        music=music,
        category=category,
        language=language,
        importance=importance,
        importance_reason=importance_reason,
        visual_analysis='',
        audio_transcription='',
        text_analysis=raw,
        content_type='youtube',
        thumbnail=result.get('thumbnail', ''),
        post_date=yt_post_date,
    )
    print(f"✓ YouTube analysis saved ({shortcode})")
    print_header("✅ Done — YouTube Analysis Complete")
    return True


def run_webpage_analysis(url: str, shortcode: str, db):
    """Fetch web page text and run AI text analysis."""
    print_section("🌐 Web Page Analysis")
    print(f"🔗 Analyzing: {url}")

    result = analyze_webpage(url)

    if result.get('error'):
        err = result['error']
        if _is_quota_error(err):
            db.queue_for_retry(shortcode, url, 'webpage', 'ai_quota', retry_hours=24)
            print("⏰ AI models quota-exhausted — queued for retry in 24 hours.")
            return RETRY_SENTINEL
        print(f"❌ Web page analysis failed: {err}")
        return

    raw = result.get('raw_output', '')
    page_title = result.get('page_title', '')
    if not raw:
        db.queue_for_retry(shortcode, url, 'webpage', 'ai_empty_response', retry_hours=1)
        print("⏰ Empty AI response — queued for retry in 1 hour.")
        return RETRY_SENTINEL

    print_section("📋 RAW AI OUTPUT")
    print(raw[:2000])

    title, summary_text, tags, music, category, language = parse_summary(raw)
    webpage_author = result.get('author', '')
    importance, importance_reason = score_importance(title, summary_text, tags, category, webpage_author)
    # Use on-page title as fallback if AI did not extract one
    if not title and page_title:
        title = page_title

    print_section("💾 Saving to Database")
    db.save_analysis(
        shortcode=shortcode,
        url=url,
        username=webpage_author,
        title=title,
        summary=summary_text,
        tags=tags,
        music=music,
        category=category,
        language=language,
        importance=importance,
        importance_reason=importance_reason,
        visual_analysis='',
        audio_transcription='',
        text_analysis=raw,
        content_type='webpage',
        thumbnail=result.get('thumbnail', ''),
        post_date=result.get('post_date'),
    )
    print(f"✓ Web page analysis saved ({shortcode})")
    print_header("✅ Done — Web Page Analysis Complete")
    return True


# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main orchestrator"""

    print_header("🧠 SUPERBRAIN - Content Analyzer")
    
    # Step 1: Get URL (+ optional --caption / --hashtags / --date-saved passed
    # by the API or the bulk importer, so source-provided context can inform
    # the summary / be stored alongside the analysis)
    #
    # --media-folder is the manual-upload escape hatch (POST /manual-upload,
    # core/manual_media.py): a folder of already-obtained media, shaped like
    # a download folder, to analyze instead of downloading from Instagram.
    source_caption = ""
    source_hashtags: list = []
    date_saved = None
    media_folder = None
    if len(sys.argv) > 1:
        instagram_url = sys.argv[1]
        print(f"📎 Link: {instagram_url}")
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--caption" and i + 1 < len(sys.argv):
                source_caption = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--hashtags" and i + 1 < len(sys.argv):
                source_hashtags = [t for t in sys.argv[i + 1].split(",") if t]
                i += 2
            elif sys.argv[i] == "--date-saved" and i + 1 < len(sys.argv):
                date_saved = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--media-folder" and i + 1 < len(sys.argv):
                media_folder = sys.argv[i + 1]
                i += 2
            else:
                i += 1
    else:
        instagram_url = input("📎 Enter URL (Instagram / YouTube / web page): ").strip()

    if not instagram_url:
        print("❌ No link provided!")
        sys.exit(1)

    # Step 2: Validate link & detect type
    print_section("🔍 Step 1: Validating Link")

    validation = validate_link(instagram_url)

    if not validation['valid']:
        print(f"❌ Invalid link!")
        print(f"   Error: {validation['error']}")
        sys.exit(1)

    content_type = validation['content_type']
    shortcode    = validation['shortcode']
    # Normalise URL (e.g. YouTube canonical form)
    instagram_url = validation['url']

    print(f"✓ Valid {content_type} link")
    print(f"  ID: {shortcode}")
    
    # Step 2.5: Check cache in database
    print_section("🔍 Step 2: Checking Cache")
    
    db = get_db()
    cached = db.check_cache(shortcode) if db.is_connected() else None
    
    if cached:
        print(f"✓ Found in cache! (Analyzed on {cached.get('analyzed_at', 'unknown')})")
        print(f"  Returning cached result...\n")
        
        # Display cached summary
        print_section("📋 CACHED RESULT")
        print(f"📌 TITLE:\n{cached.get('title', 'N/A')}\n")
        print(f"📝 SUMMARY:\n{cached.get('summary', 'N/A')}\n")
        print(f"🏷️ TAGS:\n{', '.join(cached.get('tags', []))}\n")
        print(f"🎵 MUSIC:\n{cached.get('music', 'N/A')}\n")
        cached_category = cached.get('category') or []
        if isinstance(cached_category, str):
            cached_category = [cached_category]
        print(f"📂 CATEGORY:\n{', '.join(cached_category) or 'N/A'}\n")
        cached_language = cached.get('language') or []
        if isinstance(cached_language, str):
            cached_language = [cached_language]
        print(f"🌐 LANGUAGE:\n{', '.join(cached_language) or 'N/A'}\n")
        print("=" * 80)
        print("✅ Retrieved from cache (no AI processing needed)")
        print("=" * 80 + "\n")
        return
    else:
        print("⚡ Not in cache - will analyze and save")

    # ── Dispatch non-Instagram types ──────────────────────────────────────────
    if content_type == 'youtube':
        result = run_youtube_analysis(instagram_url, shortcode, db)
        if result == RETRY_SENTINEL:
            sys.exit(2)
        if result is None:
            # Analysis failed — exit non-zero so api.py returns a proper error
            sys.exit(1)
        return
    elif content_type == 'webpage':
        result = run_webpage_analysis(instagram_url, shortcode, db)
        if result == RETRY_SENTINEL:
            sys.exit(2)
        if result is None:
            # Analysis failed — exit non-zero so api.py returns a proper error
            sys.exit(1)
        return
    # Instagram falls through to the existing pipeline below

    # Step 3: Download content
    print_section("📥 Step 3: Downloading Content")
    
    if media_folder:
        print(f"Using manually supplied media (skipping download): {media_folder}")
    else:
        print("Running Instagram downloader...")
    
    try:
        # Pass URL via stdin simulation
        import contextlib
        from io import StringIO
        
        # Import the downloader function
        from instagram.instagram_downloader import download_instagram_content, RetryableDownloadError
        
        # A hand-supplied folder short-circuits the download entirely — it is
        # already shaped like one (core/manual_media.py), so every step below
        # (glob, analyze, relocate to media/<shortcode>/) is unchanged.
        download_result = media_folder or download_instagram_content(instagram_url)
        
        if download_result is None:
            print("❌ Download failed!")
            sys.exit(1)
        
        download_folder = download_result
        if media_folder:
            print(f"\n✓ Using media at: {download_folder}")
        else:
            print(f"\n✓ Content downloaded to: {download_folder}")

    except RetryableDownloadError as e:
        msg = str(e)
        print(f"⏰ Instagram download blocked — {msg}")
        if "login required" in msg.lower():
            print("❌ Instagram now requires login for this post.")
            print("   Add INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in setup (Step 3) and retry.")
            sys.exit(1)
        db.queue_for_retry(shortcode, instagram_url, 'instagram', 'instagram_rate_limit', retry_hours=24)
        print("⏰ Queued for retry in 24 hours.")
        sys.exit(2)
        
    except Exception as e:
        print(f"❌ Download error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Step 4: Find downloaded files
    print_section("📂 Step 3: Locating Files")
    
    folder_path = Path(download_folder)
    
    if not folder_path.exists():
        print(f"❌ Folder not found: {download_folder}")
        sys.exit(1)
    
    # Find files
    mp4_files = list(folder_path.glob("*.mp4"))
    mp3_files = list(folder_path.glob("*_audio.mp3"))
    jpg_files = list(folder_path.glob("*.jpg"))
    info_files = list(folder_path.glob("info.txt"))
    
    print(f"📹 Videos: {len(mp4_files)}")
    print(f"🎵 Audio files: {len(mp3_files)}")
    print(f"🖼️  Images: {len(jpg_files)}")
    print(f"📄 Info files: {len(info_files)}")

    # A manual-upload folder that has gone empty means relocate_to_media_store()
    # already moved its files into media/<shortcode>/ on an earlier run — which
    # happens on the audio-transcription retry path (exit 2), leaving a queued
    # retry pointing at an emptied folder. Analyzing that would save a post with
    # no visual, no transcript and no caption. Fail loudly and let the user
    # re-upload instead.
    if media_folder and not (mp4_files or jpg_files):
        print("❌ No media found in the supplied folder — the uploaded file has "
              "already been consumed by an earlier run. Upload it again.")
        sys.exit(1)
    
    # Step 5: Run analyses with SMART PARALLEL PROCESSING
    print_section("🚀 Step 4: Running Parallel Analysis")
    print("Strategy: Heavy tasks sequential, light tasks parallel")
    print("Heavy: Visual (video processing), Audio (Whisper)")
    print("Light: Music (Shazam), Text (metadata)")
    
    # Guard the whole analysis phase so a bug anywhere in it (parsing,
    # summary generation, thumbnail extraction, embedding) can't crash the
    # process before the downloaded media is relocated out of temp/ below —
    # that would silently orphan the download forever. On failure we still
    # relocate whatever was downloaded (so it isn't lost/orphaned) before
    # exiting non-zero, same as any other pipeline failure.
    try:
        results = {
            'visual': [],
            'audio_transcription': [],
            'music_identification': [],
            'text': []
        }
    
        all_tasks = []
        analysis_start = time.time()
    
        # === PHASE 1: Visual Analysis (HEAVY) - Run alone ===
        # In ANALYSIS_MODE=batch, visual analysis is deferred to the
        # analysis-batch submission below (bundled with text analysis into
        # one OpenAI Batch API job) instead of running synchronously here —
        # skip this phase entirely in that mode.
        if ANALYSIS_MODE != "batch" and (mp4_files or jpg_files):
            print(f"\n🎬 Phase 1: Visual Analysis (Heavy Task)")
        
            for video in mp4_files:
                result = run_analysis_task("Visual", 'analyzers/visual_analyze.py', str(video), "heavy")
                if result['success']:
                    results['visual'].append({
                        'file': result['file'],
                        'type': 'video',
                        'output': result['output']
                    })
                    print(_clean_visual(result['output'])[:600] + "\n")
        
            for img in jpg_files:
                result = run_analysis_task("Visual", 'analyzers/visual_analyze.py', str(img), "heavy")
                if result['success']:
                    results['visual'].append({
                        'file': result['file'],
                        'type': 'image',
                        'output': result['output']
                    })
                    print(_clean_visual(result['output'])[:600] + "\n")
    
        # === PHASE 2: Audio Transcription (HEAVY) - Run alone ===
        audio_transcription_failed = False
        if mp3_files:
            print(f"\n🎙️ Phase 2: Audio Transcription (Heavy Task)")

            for audio in mp3_files:
                result = run_analysis_task("Audio", 'analyzers/audio_transcribe.py', str(audio), "heavy")
                if result['success']:
                    results['audio_transcription'].append({
                        'file': result['file'],
                        'output': result['output']
                    })
                    print(_clean_audio(result['output'])[:600] + "\n")
                else:
                    # Both Groq and local Whisper failed for this file — don't
                    # save a post with a missing/garbled transcript, queue the
                    # whole item for retry instead (same pattern as the
                    # YouTube/webpage quota-error paths below).
                    audio_transcription_failed = True
                    print(f"  ✗ Audio transcription failed for {result['file']}: {result['error'][:300]}\n")

        if audio_transcription_failed:
            print("⏰ Audio transcription failed (Groq + local Whisper both unavailable) — queuing for retry.")
            relocate_to_media_store(download_folder, shortcode)
            db.queue_for_retry(shortcode, instagram_url, 'instagram', 'audio_transcription_failed', retry_hours=6)
            sys.exit(2)

        # === PHASE 3: Light tasks in PARALLEL ===
        print(f"\n⚡ Phase 3: Light Tasks (Parallel Execution)")
    
        light_tasks = []
    
        # Add music identification tasks
        for audio in mp3_files:
            light_tasks.append(('music', 'analyzers/music_identifier.py', str(audio)))

        # Add text analysis tasks — deferred to the analysis-batch submission
        # below in ANALYSIS_MODE=batch (bundled with visual analysis into one
        # OpenAI Batch API job), same reasoning as Phase 1 above.
        if ANALYSIS_MODE != "batch":
            for info_file in info_files:
                light_tasks.append(('text', 'analyzers/text_analyzer.py', str(info_file)))
    
        if light_tasks:
            # Run light tasks in parallel (max 3 concurrent)
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}
            
                for task_type, script, file_path in light_tasks:
                    task_name = "Music ID" if task_type == 'music' else "Text"
                    future = executor.submit(run_analysis_task, task_name, script, file_path, "light")
                    futures[future] = task_type
            
                # Collect results as they complete
                for future in as_completed(futures):
                    task_type = futures[future]
                    result = future.result()
                
                    if result['success']:
                        if task_type == 'music':
                            results['music_identification'].append({
                                'file': result['file'],
                                'output': result['output']
                            })
                        else:  # text
                            results['text'].append({
                                'file': result['file'],
                                'output': result['output']
                            })
                    
                        if task_type == 'music':
                            print(result['output'][:400] + "\n")
                        else:
                            print(_clean_text(result['output'])[:600] + "\n")
    
        analysis_elapsed = time.time() - analysis_start
        print(f"\n⏱️  Total Analysis Time: {analysis_elapsed:.1f}s")

        # === ANALYSIS_MODE=batch: submit visual + text analysis to OpenAI's
        # Batch API too, not just the summary — both are normally OpenAI
        # vision/text calls at full synchronous price (audio transcription
        # is Groq/local Whisper and music ID is Shazam, neither ever touches
        # OpenAI, so Phases 2-3 above still ran those synchronously as
        # usual). Bundles one vision request per video/image file plus one
        # text-analysis request into a SINGLE batch job (all
        # /v1/chat/completions), mirroring visual_analyze.py's/
        # text_analyzer.py's own prompt-building exactly so results parse
        # identically once the batch resolves (see core/batch_processor.py's
        # _advance_analysis_phase()).
        if ANALYSIS_MODE == "batch" and (mp4_files or jpg_files or info_files):
            print_header("📦 SUBMITTING TO OPENAI BATCH (visual + text analysis)")
            from core.model_router import get_router as _get_router
            from analyzers.visual_analyze import (
                extract_frames, image_to_b64, VISION_PROMPT,
                _get_duration_s, _frame_count_for_duration,
            )
            from analyzers.text_analyzer import build_text_analysis_prompt

            router = _get_router()
            analysis_requests = []
            visual_files_meta = []  # [{"file":..., "type":...}, ...] in submission order

            for video in mp4_files:
                duration = _get_duration_s(str(video))
                max_frames = _frame_count_for_duration(duration)
                print(f"🎥 Extracting frames from {video.name}... (~{duration}s → {max_frames} frame(s))")
                frames = extract_frames(str(video), max_frames=max_frames)
                if frames:
                    custom_id = f"visual__{len(visual_files_meta)}"
                    analysis_requests.append(
                        router.build_batch_vision_request(custom_id, VISION_PROMPT, frames)
                    )
                    visual_files_meta.append({"file": video.name, "type": "video"})
                else:
                    print(f"⚠️  Could not extract any frames from {video.name} — skipping")

            for img in jpg_files:
                try:
                    frame = image_to_b64(str(img))
                except Exception as e:
                    print(f"⚠️  Could not load image {img.name}: {e}")
                    continue
                custom_id = f"visual__{len(visual_files_meta)}"
                analysis_requests.append(
                    router.build_batch_vision_request(custom_id, VISION_PROMPT, [frame])
                )
                visual_files_meta.append({"file": img.name, "type": "image"})

            text_file_name = None
            if info_files:
                try:
                    with open(info_files[0], 'r', encoding='utf-8') as f:
                        info_content = f.read().strip()
                except Exception as e:
                    info_content = ""
                    print(f"⚠️  Could not read {info_files[0].name}: {e}")
                if info_content:
                    text_prompt = build_text_analysis_prompt(info_content)
                    analysis_requests.append(router.build_batch_chat_request("text", text_prompt))
                    text_file_name = info_files[0].name

            if analysis_requests:
                analysis_batch_id = router.submit_openai_batch(analysis_requests, endpoint="/v1/chat/completions")

                instagram_thumbnail = extract_instagram_thumbnail(jpg_files, mp4_files)
                _info = parse_info_txt(info_files)
                media_files = relocate_to_media_store(download_folder, shortcode)
                audio_text = "\n\n".join([_clean_audio(r['output']) for r in results['audio_transcription']])
                transcription_backend = (
                    _audio_backend(results['audio_transcription'][0]['output'])
                    if results['audio_transcription'] else ""
                )

                state = {
                    "source_caption": source_caption,
                    "source_hashtags": source_hashtags,
                    "date_saved": date_saved,
                    "username": _info["username"],
                    "likes": _info["likes"],
                    "post_date": _info["post_date"],
                    "caption": _info["caption"],
                    "media_files": media_files,
                    "visual_files": visual_files_meta,
                    "text_file": text_file_name,
                    "audio_text": audio_text,
                    "transcription_backend": transcription_backend,
                    "thumbnail": instagram_thumbnail,
                    "music_identification": results.get('music_identification', []),
                    "content_type": "instagram",
                }
                db.enqueue_analysis_batch_job(shortcode, instagram_url, "instagram", analysis_batch_id, json.dumps(state))
                print(f"📦 Submitted to OpenAI batch (visual+text analysis): {analysis_batch_id}")
                sys.exit(BATCH_EXIT_CODE)
            # else: nothing extractable (e.g. all files corrupt/unreadable) —
            # fall through to the summary-only batch path below with empty
            # visual/text content, same as the "no media at all" case.

        # === ANALYSIS_MODE=batch fallback: reached only when there was
        # nothing for the analysis-batch block above to submit (no video/
        # image files AND no info.txt — rare) or `analysis_requests` ended
        # up empty (all files corrupt/unreadable). Submits the combined
        # summary directly with whatever's actually available (results
        # still has empty visual/text lists in this case), same as the
        # immediate pipeline would produce for such a post. This subprocess
        # won't be alive when the batch completes — resumption happens
        # in-process in api.py via core/batch_processor.check_and_advance_batches(),
        # called on backend startup and from POST /batches/check, not here.
        if ANALYSIS_MODE == "batch":
            print_header("📦 SUBMITTING TO OPENAI BATCH (summary)")
            from core.model_router import get_router as _get_router

            instagram_thumbnail = extract_instagram_thumbnail(jpg_files, mp4_files)
            _info = parse_info_txt(info_files)
            media_files = relocate_to_media_store(download_folder, shortcode)

            visual_text = "\n\n".join([_clean_visual(r['output']) for r in results['visual']])
            audio_text = "\n\n".join([_clean_audio(r['output']) for r in results['audio_transcription']])
            text_text = "\n\n".join([_clean_text(r['output']) for r in results['text']])
            transcription_backend = (
                _audio_backend(results['audio_transcription'][0]['output'])
                if results['audio_transcription'] else ""
            )

            prompt = build_final_summary_prompt(results, instagram_url, source_caption, source_hashtags)
            router = _get_router()
            batch_req = router.build_batch_chat_request(shortcode, prompt)
            summary_batch_id = router.submit_openai_batch([batch_req], endpoint="/v1/chat/completions")

            state = {
                "source_caption": source_caption,
                "source_hashtags": source_hashtags,
                "date_saved": date_saved,
                "username": _info["username"],
                "likes": _info["likes"],
                "post_date": _info["post_date"],
                "caption": _info["caption"],
                "media_files": media_files,
                "visual_text": visual_text,
                "audio_text": audio_text,
                "text_text": text_text,
                "transcription_backend": transcription_backend,
                "thumbnail": instagram_thumbnail,
                "music_identification": results.get('music_identification', []),
                "content_type": "instagram",
            }
            db.enqueue_batch_job(shortcode, instagram_url, "instagram", summary_batch_id, json.dumps(state))
            print(f"📦 Submitted to OpenAI batch (summary): {summary_batch_id}")
            sys.exit(BATCH_EXIT_CODE)

        # Final comprehensive summary
        print_header("✅ GENERATING COMPREHENSIVE SUMMARY")

        final_summary, model_used = generate_final_summary(results, instagram_url, source_caption, source_hashtags)
    
        print_section("📋 FINAL REPORT")
        print(final_summary)
    
        # Extract structured data from summary for database
        title, summary_text, tags, music, category, language = parse_summary(final_summary)
    
        # OVERRIDE LLM MUSIC WITH DIRECT SHAZAM OUTPUT TO PRESERVE LINKS
        music = apply_music_override(music, results.get('music_identification'))

        # Get additional metadata from info.txt if available
        _info = parse_info_txt(info_files)
        username = _info["username"]
        likes = _info["likes"]
        post_date = _info["post_date"]
        caption = _info["caption"]

        importance, importance_reason = score_importance(title, summary_text, tags, category, username)

        # Save to database
        print_section("💾 Saving to Database")

        # Combine analysis texts — extract clean content (not raw stdout)
        visual_text = "\n\n".join([_clean_visual(r['output']) for r in results['visual']])
        audio_text = "\n\n".join([_clean_audio(r['output']) for r in results['audio_transcription']])
        text_text = "\n\n".join([_clean_text(r['output']) for r in results['text']])
        transcription_backend = (
            _audio_backend(results['audio_transcription'][0]['output'])
            if results['audio_transcription'] else ""
        )

        # — Instagram thumbnail: first downloaded jpg (converted to base64), or
        # first frame of the first video —
        instagram_thumbnail = extract_instagram_thumbnail(jpg_files, mp4_files)

        # Generate an embedding for semantic search (best-effort — a failure here
        # shouldn't fail the whole analysis, the post just won't be
        # semantically-searchable until a later backfill).
        embedding = None
        try:
            from core.model_router import get_router as _get_router
            embedding_text = f"{title}\n\n{summary_text}\n\nTags: {', '.join(tags)}"
            embedding = _get_router().generate_embedding(embedding_text)
            if embedding:
                print(f"✓ Generated embedding ({len(embedding)} dims)")
        except Exception as emb_err:
            print(f"⚠️  Embedding generation error: {emb_err}")
    except Exception as e:
        print(f"\n❌ Analysis pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        print_section("🎞️  Relocating media to permanent storage (after failure)")
        relocate_to_media_store(download_folder, shortcode)
        sys.exit(1)


    # Move the downloaded video/audio/thumbnail out of temp/ (caption-named,
    # transient) into media/<shortcode>/ (stable, permanent) — this is what
    # lets a future "watch original video" screen find a post's files without
    # depending on Instagram still hosting them. Must happen after the
    # thumbnail/frame extraction above, which still reads from temp/.
    print_section("🎞️  Relocating media to permanent storage")
    media_files = relocate_to_media_store(download_folder, shortcode)
    if media_files:
        print(f"✓ Moved {len(media_files)} file(s) to media/{shortcode}/: {', '.join(media_files)}")
    else:
        print("⚠ No media files relocated (nothing found in temp folder, or move failed)")

    saved = db.save_analysis(
        shortcode=shortcode,
        url=instagram_url,
        username=username,
        title=title,
        summary=summary_text,
        tags=tags,
        music=music,
        category=category,
        language=language,
        importance=importance,
        importance_reason=importance_reason,
        media_files=media_files,
        visual_analysis=visual_text,
        audio_transcription=audio_text,
        text_analysis=text_text,
        likes=likes,
        post_date=post_date,
        thumbnail=instagram_thumbnail,
        source_hashtags=source_hashtags,
        embedding=embedding,
        model_used=model_used,
        transcription_backend=transcription_backend,
        caption=caption,
        date_saved=date_saved,
    )

    if not saved:
        # save_analysis() already printed the underlying error. Exit non-zero
        # so api.py/queue_worker treat this as a failure instead of silently
        # marking the item complete — the media was already relocated above,
        # but with no DB row pointing at it (and the caller can decide whether
        # to have the user retry).
        print("❌ Analysis pipeline succeeded but the database write failed — see error above.")
        sys.exit(1)

    print(f"✓ Analysis saved to database")
    print("\n" + "=" * 80)
    print(f"📊 Analyses Complete: Visual({len(results['visual'])}), Audio({len(results['audio_transcription'])}), Music({len(results['music_identification'])}), Text({len(results['text'])})")
    print(f"⏱️  Total Time: {analysis_elapsed:.1f}s")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
