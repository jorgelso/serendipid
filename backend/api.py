"""
SuperBrain Instagram Content Analysis API
Version: 1.03
FastAPI REST endpoints for analyzing Instagram content with MongoDB caching
With request queuing, live progress logging, and API key authentication
"""

from fastapi import FastAPI, HTTPException, Query, Header, Depends, Request, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
import subprocess
import asyncio
import sys
import os
import json
import re
import uuid
import shutil
import zipfile
import io
from datetime import datetime
import logging
import secrets
import string
import threading
import time
from pathlib import Path


def _load_env_file():
    """Load backend/.env into the process environment, if present. Real env
    vars (already set by the shell, a launcher script, or Docker) always
    take precedence — this only fills in what's not already set, so it's a
    no-op for anyone not using a .env file (the pre-existing behavior).
    Hand-rolled instead of adding python-dotenv as a dependency for ~15
    lines of parsing. Must run before any local module is imported below,
    since some (e.g. core.database's DATABASE_PATH) read env vars at
    import time."""
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

# Import database module
from core.database import get_db
from core.link_checker import validate_link
from core.model_router import get_router
from core.categories import CATEGORIES
from core.importance import score_and_stamp_importance
from core import rag
from core import study_guide
from core import study_guide_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def generate_api_token(length=8):
    """Generate an 8-character alphanumeric Access Token."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def is_valid_api_token_format(token: str) -> bool:
    """Validate token format: exactly 8 alphanumeric chars."""
    return len(token) == 8 and token.isalnum()

TOKEN_FILE = Path(__file__).parent / "token.txt"

# The port this API process itself listens on when run directly
# (`python api.py`, the uvicorn.run() call at the bottom of this file) — also
# hardcoded to the same value in start.py's PORT constant (5000 collides with
# macOS AirPlay Receiver, see start.py's comment). Not configurable via env
# var today. Kept as one named constant so the /instagram-export/jobs
# subprocess spawner (below) builds its --server-url from the same source of
# truth instead of a second hardcoded literal.
API_SELF_PORT = 5050

# 202 from /analyze (and /manual-upload) means two completely different
# things — "Instagram blocked the download, a retry is scheduled" and
# "submitted to OpenAI's Batch API, this is working and will land within
# 24h" — and a caller that can't tell them apart reports a perfectly
# successful batch submission as a failure. This header carries the
# distinction; `detail` stays a plain string so no existing consumer (the
# import scripts, the mobile app) sees any change at all.
#
# Values: "retry_scheduled" (main.py exit 2) | "batch_submitted" (exit 3).
ANALYSIS_OUTCOME_HEADER = "X-Superbrain-Outcome"

# Ceiling on how long a single Instagram analysis subprocess (main.py) is allowed
# to run before being force-killed. Default raised from the original 600s (10 min)
# to give slower hardware (e.g. a Raspberry Pi falling back to local Whisper when
# Groq is unavailable) enough headroom. Override via env var if needed.
ANALYSIS_SUBPROCESS_TIMEOUT = int(os.getenv("ANALYSIS_SUBPROCESS_TIMEOUT", "1200"))

# main.py reads its own copy of this (it's a separate subprocess) to decide
# whether to submit the combined-summary call to OpenAI's Batch API instead
# of calling it synchronously — see main.py and core/batch_processor.py.
# Read here too, only for /queue-status reporting and to know whether the
# exit-code-3 branches below are expected to ever fire.
ANALYSIS_MODE = os.getenv("ANALYSIS_MODE", "immediate").strip().lower()

# Same class of ceiling as ANALYSIS_SUBPROCESS_TIMEOUT above, but for a
# single-shortcode `scripts/rescan_post.py <shortcode>` run (POST
# /reanalyze/bulk's synchronous single-item path — see "Rescan pipeline" in
# backend/CLAUDE.md). Not used for the --batch/background path, which has no
# HTTP caller waiting on it and so has no timeout.
RESCAN_SUBPROCESS_TIMEOUT = int(os.getenv("RESCAN_SUBPROCESS_TIMEOUT", "1200"))

def load_or_create_api_token():
    """Load existing API token or create one if missing."""
    if TOKEN_FILE.exists():
        content = TOKEN_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        if content and is_valid_api_token_format(content):
            logger.info("=" * 80)
            logger.info(f"🔐 API Token: {content}")
            logger.info("=" * 80)
            return content

        if content:
            logger.warning("Existing token format is legacy/invalid. Regenerating 8-character Access Token.")

    token = generate_api_token()
    TOKEN_FILE.write_text(token)

    logger.info("=" * 80)
    logger.info(f"🔐 API Token (NEW): {token}")
    logger.info("=" * 80)
    return token

API_TOKEN = load_or_create_api_token()

async def verify_token(request: Request, x_api_key: str = Header(None, description="Access Token for authentication")):
    """
    Verify authentication using Access Token.
    Can be passed in X-API-Key header or token query parameter.
    """
    actual_token = x_api_key or request.query_params.get("token")
    if actual_token != API_TOKEN:
        logger.warning("Invalid Access Token attempt from IP: %s", request.client.host if hasattr(request, 'client') and request.client else 'unknown')
        raise HTTPException(
            status_code=401,
            detail="Invalid Access Token. Use the token from backend/token.txt."
        )
    return actual_token

# Initialize FastAPI app
app = FastAPI(
    title="SuperBrain",
    description="AI-powered Instagram content analysis with caching",
    version="1.03"
)

# CORS configuration
import os

# Get allowed origins from environment variable or allow all for development
allowed_origins_env = os.getenv('ALLOWED_ORIGINS', '')
if allowed_origins_env:
    allowed_origins = [origin.strip() for origin in allowed_origins_env.split(',')]
else:
    # Development: allow all origins so phones on same WiFi can connect
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False if allowed_origins == ["*"] else True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # CSP - adjust based on your needs
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    return response

# Request queue management (persistent)
max_concurrent = 1  # Process one post at a time - queue others sequentially

# Track active analysis subprocesses so they can be killed on delete
_active_processes: dict = {}        # shortcode -> subprocess.Popen
_active_processes_lock = threading.Lock()

# Guards the "is there capacity? -> claim it" admission decision shared by the
# /analyze fast path and queue_worker's background pickup. Without this, both
# can independently read get_processing()/get_queue() as having spare
# capacity at the same moment and both start a main.py subprocess, silently
# breaking the max_concurrent=1 guarantee below.
_queue_admission_lock = threading.Lock()

_STATIC_DIR = Path(__file__).parent / "static"
_THUMBNAILS_DIR = _STATIC_DIR / "thumbnails"
_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

from core.media_store import MEDIA_DIR
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
# Permanently-relocated post media (video/audio/thumbnail) — see
# core/media_store.py. Same unauthenticated-static-file pattern as /static
# above; not gated by the API token like the JSON endpoints are. Fine for a
# server bound to localhost, but worth knowing if this ever gets tunneled
# (e.g. ngrok) somewhere reachable by more than just you.
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = _STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    from fastapi.responses import Response
    return Response(status_code=204)

# Shared Instaloader instance for caption fetching (reuse session to avoid rate limits)
caption_loader = None
caption_loader_lock = threading.Lock()

def get_caption_loader():
    """Get or create shared Instaloader instance for caption fetching"""
    global caption_loader
    with caption_loader_lock:
        if caption_loader is None:
            import instaloader
            caption_loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                max_connection_attempts=1  # Fail fast
            )
        return caption_loader

# Initialize database and recover interrupted items on startup
db = get_db()
if db.is_connected():
    recovered = db.recover_interrupted_items()
    if recovered > 0:
        logger.info(f"🔄 Recovered {recovered} interrupted items from previous session")

    # Any /instagram-export/jobs row still 'running' from before this process
    # started is stale — its subprocess died with the previous process. The
    # underlying import_state.json resume state isn't affected.
    stale_jobs = db.mark_stale_import_jobs_failed()
    if stale_jobs > 0:
        logger.info(f"🔄 Marked {stale_jobs} stale import job(s) as failed (server restarted mid-run)")

# Check for any OpenAI batch jobs (ANALYSIS_MODE=batch) that completed while
# this backend was offline. Runs once here (not periodically — batch mode is
# checked on startup and on-demand only, see POST /batches/check below) in a
# background thread so a slow OpenAI round-trip never delays server readiness.
def _startup_batch_check():
    try:
        from core.batch_processor import check_and_advance_batches
        result = check_and_advance_batches()
        logger.info(f"📦 Startup batch check: {result}")
    except Exception as e:
        logger.error(f"Startup batch check failed: {e}")

threading.Thread(target=_startup_batch_check, daemon=True).start()

# Same idea, for the separate rescan-batch pipeline (core/rescan_batch_processor.py) —
# a distinct check, not a call into check_and_advance_batches() above.
def _startup_rescan_batch_check():
    try:
        from core.rescan_batch_processor import check_and_advance_rescan_batches
        result = check_and_advance_rescan_batches()
        logger.info(f"📦 Startup rescan-batch check: {result}")
    except Exception as e:
        logger.error(f"Startup rescan-batch check failed: {e}")

threading.Thread(target=_startup_rescan_batch_check, daemon=True).start()

# Same idea, for scripts/score_eloquence.py --batch's batch pipeline
# (core/eloquence_batch_processor.py) — also its own distinct check, not a
# call into either check above.
def _startup_eloquence_batch_check():
    try:
        from core.eloquence_batch_processor import check_and_advance_eloquence_batches
        result = check_and_advance_eloquence_batches()
        logger.info(f"📦 Startup eloquence-batch check: {result}")
    except Exception as e:
        logger.error(f"Startup eloquence-batch check failed: {e}")

threading.Thread(target=_startup_eloquence_batch_check, daemon=True).start()

# Background worker to process queue
def queue_worker():
    """Background thread that processes queued items automatically"""
    logger.info("🔧 Queue worker thread started")
    _retry_check_counter = 0
    
    while True:
        try:
            # ── Periodic retry-queue drain (every ~2.5 min) ─────────────────
            _retry_check_counter += 1
            if _retry_check_counter >= 30:
                _retry_check_counter = 0
                ready = db.get_retry_ready()
                if ready:
                    logger.info(f"🔄 Promoting {len(ready)} retry-ready item(s) back to queue")
                    for r_item in ready:
                        logger.info(
                            f"   ↩ {r_item['shortcode']} "
                            f"(reason={r_item['reason']}, attempts={r_item['attempts']})"
                        )
                        db.add_to_queue(r_item['shortcode'], r_item['url'])

            # Check if we have capacity and claim the next queued item, if
            # any, atomically — held together so a concurrent /analyze fast
            # path can't slip in between the capacity check and the claim.
            item = None
            with _queue_admission_lock:
                processing = db.get_processing()
                if len(processing) < max_concurrent:
                    queue = db.get_queue()
                    if queue:
                        item = queue[0]  # Get first item
                        shortcode = item['shortcode']
                        url = item['url']
                        db.mark_processing(shortcode, url)

            if item:
                logger.info(f"📋 Queue alert: Processing next in queue")
                logger.info(f"📊 Queue status: {len(queue) - 1} remaining after this | Starting: {shortcode}")
                logger.info(f"📤 [{shortcode}] Starting analysis from queue...")

                # Run analysis
                try:
                    cmd = [sys.executable, "main.py", url]
                    if item.get('caption'):
                        cmd += ["--caption", item['caption']]
                    if item.get('hashtags'):
                        cmd += ["--hashtags", ",".join(item['hashtags'])]
                    if item.get('date_saved'):
                        cmd += ["--date-saved", item['date_saved']]
                    if item.get('media_folder'):
                        cmd += ["--media-folder", item['media_folder']]
                    process = subprocess.Popen(
                        cmd,
                        cwd=Path(__file__).parent,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        bufsize=1
                    )

                    # Register so delete_post can kill it
                    with _active_processes_lock:
                        _active_processes[shortcode] = process

                    # Wait for completion
                    try:
                        process.wait(timeout=ANALYSIS_SUBPROCESS_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        logger.error(f"❌ [{shortcode}] Process timed out after {ANALYSIS_SUBPROCESS_TIMEOUT}s. Killing...")
                        process.kill()
                        process.wait()
                        db.remove_from_queue(shortcode)
                        continue

                    with _active_processes_lock:
                        _active_processes.pop(shortcode, None)

                    # If the post was deleted while processing, skip queue cleanup
                    # (delete_post already called remove_from_queue)
                    if process.returncode == -9 or process.returncode == -15:
                        logger.info(f"🛑 [{shortcode}] Analysis killed (post was deleted)")
                    elif process.returncode == 0:
                        logger.info(f"✅ Queue item completed: {shortcode}")
                        db.remove_from_queue(shortcode)
                    elif process.returncode == 2:
                        # main.py queued this item for retry — status already set in DB
                        logger.info(f"⏰ [{shortcode}] Quota exhausted — moved to retry queue")
                        db.remove_from_queue(shortcode)
                    elif process.returncode == 3:
                        # main.py submitted this item to OpenAI's Batch API
                        # (ANALYSIS_MODE=batch) — db.enqueue_batch_job() already
                        # set processing_queue.status='batch'. Do NOT remove it;
                        # core/batch_processor.check_and_advance_batches() (run
                        # on startup / POST /batches/check) finishes the item
                        # later and removes the row itself once saved.
                        logger.info(f"📦 [{shortcode}] Submitted to OpenAI batch — leaving as batch-pending")
                    else:
                        logger.error(f"❌ Queue item failed (rc={process.returncode}): {shortcode}")
                        db.remove_from_queue(shortcode)

                except Exception as e:
                    with _active_processes_lock:
                        _active_processes.pop(shortcode, None)
                    logger.error(f"❌ Error processing queue item {shortcode}: {e}")
                    db.remove_from_queue(shortcode)
            
            # Sleep before next check
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            time.sleep(10)

# Start worker thread
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()
logger.info("✅ Background queue worker initialized")

# Request/Response models
class AnalyzeRequest(BaseModel):
    url: str
    force: bool = False
    # Explicit intent required to bring a soft-deleted post back. Without
    # this, resubmitting a shortcode that's is_hidden=1 (e.g. an automated
    # import/sync script re-encountering it) is a no-op — see the 410 branch
    # in analyze_content(). Deliberate user actions (sharing a URL again,
    # re-saving from Instagram) should set this to True.
    restore: bool = False
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    # The real date this post was saved to Instagram (NOT its publish date) —
    # looked up by scripts/import_saved_instagram.py from saved_posts.json
    # and threaded through exactly like caption/hashtags above. Ignored by
    # every other client (mobile app, browser extension, direct URL shares),
    # same as caption/hashtags already are. See analyses.date_saved's
    # migration comment in core/database.py for the full story.
    date_saved: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.instagram.com/p/DRWKk5JiL0h/",
                "force": False,
                "restore": False,
                "caption": None,
                "hashtags": None,
                "date_saved": None
            }
        }

class AnalysisResponse(BaseModel):
    success: bool
    cached: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None


class BulkReanalyzeRequest(BaseModel):
    shortcodes: List[str]


class BulkReanalyzeError(BaseModel):
    shortcode: str
    error: str


class BulkReanalyzeResponse(BaseModel):
    success: bool
    rescored: List[str]  # cheap importance-only rescore, already done synchronously
    queued: List[str]    # full re-analysis, now in processing_queue (async)
    errors: List[BulkReanalyzeError]


# API Endpoints

@app.get("/")
async def root():
    """API information and health check (no authentication required)"""
    
    backend_id = "unknown"
    backend_id_path = get_config_path("backend_id.txt")
    if backend_id_path.exists():
        backend_id = backend_id_path.read_text().strip()
    
    return {
        "backendId": backend_id,

        "name": "SuperBrain Instagram Analyzer API",
        "version": "1.03",
        "status": "operational",
        "authentication": "Required - Use Access Token with X-API-Key header",
        "message": "Run start.py on the server and use the token from token.txt.",
        "endpoints": {
            "POST /analyze": "Analyze content (requires auth)",
            "GET /caption": "Get post caption quickly (requires auth)",
            "GET /cache/{shortcode}": "Check cache (requires auth)",
            "GET /recent": "Get recent analyses (requires auth)",
            "GET /stats": "Database statistics (requires auth)",
            "GET /category/{category}": "Get by category (requires auth)",
            "GET /search": "Search by tags (requires auth)"
        }
    }


@app.get("/caption")
async def get_caption(url: str, token: str = Depends(verify_token)):
    """
    Quick caption fetch - calls caption.py as subprocess
    Simple and works every time
    """
    try:
        logger.info(f"🔍 Quick caption fetch for: {url}")
        
        # Extract shortcode for logging
        validation = validate_link(url)
        shortcode = validation['shortcode']
        
        # Run caption.py as subprocess - simple and reliable
        import subprocess
        import sys
        
        loop = asyncio.get_event_loop()
        
        def run_caption_script():
            # Use the same Python interpreter as the API (with all packages)
            python_exe = sys.executable
            print(f"[API] Using Python: {python_exe}")
            
            result = subprocess.run(
                [python_exe, 'analyzers/caption.py', url],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=15,
                cwd=str(Path(__file__).parent)
            )
            print(f"[API] Subprocess stdout: {repr(result.stdout[:200])}")
            print(f"[API] Subprocess stderr: {repr(result.stderr[:200])}")
            print(f"[API] Subprocess returncode: {result.returncode}")
            return result.stdout.strip() if result.stdout else ""
        
        try:
            caption_text = await asyncio.wait_for(
                loop.run_in_executor(None, run_caption_script),
                timeout=20.0
            )
        except asyncio.TimeoutError:
            logger.error(f"❌ [{shortcode}] Caption fetch timed out")
            return {
                "success": True,
                "shortcode": shortcode,
                "username": "",
                "title": "Instagram Post",
                "full_caption": ""
            }
        
        print(f"[API] Final caption_text: {repr(caption_text)}")
        
        # Check if it's an error message
        if caption_text.startswith('❌') or caption_text.startswith('ℹ️'):
            logger.warning(f"⚠️ [{shortcode}] {caption_text}")
            return {
                "success": True,
                "shortcode": shortcode,
                "username": "",
                "title": "Instagram Post",
                "full_caption": ""
            }
        
        # Limit to 100 chars for title
        title = caption_text[:100] if len(caption_text) > 100 else caption_text
        title = title if title else "Instagram Post"
        
        logger.info(f"✅ [{shortcode}] Caption: {title}")
        
        return {
            "success": True,
            "shortcode": shortcode,
            "username": "",
            "title": title,
            "full_caption": caption_text
        }
        
    except Exception as e:
        logger.error(f"❌ Caption fetch failed: {str(e)}", exc_info=True)
        return {
            "success": True,
            "shortcode": "",
            "username": "",
            "title": "Instagram Post",
            "full_caption": "",
            "error": str(e)
        }


async def _run_or_queue_analysis(
    shortcode: str,
    url_str: str,
    content_type: str,
    caption: Optional[str] = None,
    hashtags: Optional[List[str]] = None,
    date_saved: Optional[str] = None,
    *,
    run_inline: bool = True,
    media_folder: Optional[str] = None,
) -> dict:
    """
    Shared by POST /analyze (called after Step 1 there has already handled
    any existing cached row — including hard-deleting it for a force
    re-analyze) and POST /reanalyze/bulk's full-reanalysis branch.

    Returns {"status": "queued", "position": N} or {"status": "ran", "data": {...}}.
    The "queued" outcome is deliberately returned, not raised as an
    HTTPException, here — raising it used to put that outcome inside the same
    try/except cleanup block as a real failure, which called
    db.remove_from_queue() on the item that had just been queued a few lines
    earlier, un-queuing it before the background queue_worker() thread (which
    polls every 5s) ever got a chance to process it. Callers decide what to
    do with a "queued" result themselves.

    run_inline=False unconditionally queues even when a processing slot is
    free, so a bulk caller's HTTP response never blocks on one item's
    multi-minute subprocess.

    media_folder (POST /manual-upload) points main.py at already-obtained
    media instead of letting it download from Instagram. It is persisted on
    the queue row like caption/hashtags/date_saved, so an upload arriving
    while something else is analyzing (max_concurrent is 1, and a bulk
    import keeps that slot busy for hours) waits its turn and still gets
    analyzed from the uploaded file rather than silently reverting to the
    download attempt that already failed.
    """
    db = get_db()

    with _queue_admission_lock:
        processing_items = db.get_processing()
        if shortcode in processing_items:
            logger.warning(f"⏳ [{shortcode}] Already being processed. Please wait...")
            raise HTTPException(
                status_code=409,
                detail="This URL is already being analyzed. Please wait and try again in a moment."
            )

        # status='batch' means main.py already did the download and the
        # expensive local work, and the AI calls are in flight in an OpenAI
        # Batch API job (ANALYSIS_MODE=batch), tracked in batch_jobs and
        # finished later by core/batch_processor.check_and_advance_batches().
        #
        # Nothing below would notice: mark_processing() would overwrite the
        # 'batch' status a few lines down and main.py would re-download and
        # re-analyze the whole reel from scratch — paying for the work twice
        # and orphaning the batch_jobs row, whose eventual completion then
        # overwrites the fresh result. The row is only removed once the batch
        # finalizes, so a plain "already in flight" refusal is correct and
        # self-clearing.
        if db.get_queue_status(shortcode) == "batch":
            logger.warning(f"📦 [{shortcode}] Already submitted to an AI batch — refusing to duplicate.")
            raise HTTPException(
                status_code=409,
                detail="This post's analysis is already in flight in an OpenAI batch and will "
                       "finish on its own (up to 24h). Re-analyzing now would duplicate the work. "
                       "Use POST /batches/check to advance it, or DELETE /queue/{shortcode} first "
                       "if you really want to start over."
            )

        queue_items = db.get_queue()
        for item in queue_items:
            if item['shortcode'] == shortcode:
                logger.info(f"🔄 [{shortcode}] Duplicate found in queue - removing old entry and processing fresh request")
                db.remove_from_queue(shortcode)
                break

        queue_items = db.get_queue()
        slot_free = len(processing_items) < max_concurrent
        if not run_inline or not slot_free:
            logger.warning(f"🚦 [{shortcode}] Server busy or queuing requested — adding to queue...")
            queue_position = db.add_to_queue(shortcode, url_str, caption, hashtags, date_saved,
                                             media_folder)
            if queue_position > 0:
                logger.info(f"📝 [{shortcode}] ✅ Added to queue at position {queue_position}")
                logger.info(f"📊 Queue status: {len(queue_items) + 1} waiting | {len(processing_items)} analyzing")
                return {"status": "queued", "position": queue_position}
            raise HTTPException(status_code=500, detail="Failed to add to queue. Please try again.")

        # Step 4: Start processing
        if len(queue_items) > 0:
            logger.info(f"📊 Queue status: {len(queue_items)} waiting | Starting: {shortcode}")
        logger.info(f"🚀 [{shortcode}] Starting analysis...")
        db.mark_processing(shortcode, url_str, content_type)

    # Run main.py as subprocess — executed in a thread pool so the asyncio
    # event loop stays free to serve /ping and other requests during analysis.
    logger.info(f"📊 [{shortcode}] Phase 1: Downloading content...")

    def _run_subprocess() -> tuple:
        cmd = [sys.executable, "main.py", url_str]
        if media_folder:
            cmd += ["--media-folder", media_folder]
        if caption:
            cmd += ["--caption", caption]
        if hashtags:
            cmd += ["--hashtags", ",".join(hashtags)]
        if date_saved:
            cmd += ["--date-saved", date_saved]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            cwd=str(Path(__file__).parent),
            bufsize=1
        )
        with _active_processes_lock:
            _active_processes[shortcode] = proc
        lines = []
        for line in proc.stdout:
            lines.append(line)
            lc = line.strip()
            if "Step 4: Visual Analysis" in lc:
                logger.info(f"🎬 [{shortcode}] Phase 2: Visual analysis (AI processing)...")
            elif "Step 5: Audio Transcription" in lc or "Phase 2: Audio" in lc:
                logger.info(f"🎙️ [{shortcode}] Phase 3: Audio transcription (Whisper)...")
            elif "Phase 3: Light Tasks" in lc:
                logger.info(f"⚡ [{shortcode}] Phase 4: Music ID + Text (parallel)...")
            elif "GENERATING COMPREHENSIVE SUMMARY" in lc:
                logger.info(f"🧠 [{shortcode}] Phase 5: Generating AI summary...")
            elif "Saving to Database" in lc:
                logger.info(f"💾 [{shortcode}] Phase 6: Saving to database...")
            elif "Cleaned up temp folder" in lc:
                logger.info(f"🗑️ [{shortcode}] Phase 7: Cleanup complete")
        proc.wait()
        with _active_processes_lock:
            _active_processes.pop(shortcode, None)
        return proc.returncode, ''.join(lines), proc.stderr.read()

    try:
        returncode, stdout, stderr = await asyncio.wait_for(
            asyncio.to_thread(_run_subprocess),
            timeout=ANALYSIS_SUBPROCESS_TIMEOUT
        )

        if stderr.strip():
            # Log stderr from main.py to help diagnose issues
            logger.warning(f"⚠️  [{shortcode}] main.py stderr:\n{stderr[:1000]}")

        if returncode == 2:
            # main.py detected quota exhaustion (Instagram block or AI) and queued item for retry.
            # NOTE: Do NOT remove from queue here — main.py already called
            # queue_for_retry() which set status='retry'. Removing would lose it.
            logger.info(f"⏰ [{shortcode}] Rate limit or quota exhausted (often Instagram blocking the download). Your request has been queued for automatic retry in 24 hours.")
            raise HTTPException(
                status_code=202,
                detail="Rate limit or quota exhausted (often Instagram blocking the download). Your request has been queued for automatic retry in 24 hours.",
                headers={ANALYSIS_OUTCOME_HEADER: "retry_scheduled"},
            )

        if returncode == 3:
            # main.py submitted this item to OpenAI's Batch API (ANALYSIS_MODE=batch).
            # NOTE: Do NOT remove from queue here — main.py already called
            # db.enqueue_batch_job() which set status='batch'. It's finished
            # later by core/batch_processor.check_and_advance_batches().
            logger.info(f"📦 [{shortcode}] Submitted for batch processing (lower cost, may take up to 24h).")
            raise HTTPException(
                status_code=202,
                detail="Submitted for batch processing (lower cost, may take up to 24h). Check back later or trigger a manual batch check.",
                headers={ANALYSIS_OUTCOME_HEADER: "batch_submitted"},
            )

        if returncode != 0:
            # Extract last meaningful error line from stdout for the error message
            error_lines = [l.strip() for l in stdout.splitlines() if l.strip() and ('❌' in l or 'Error' in l or 'failed' in l.lower())]
            error_detail = error_lines[-1] if error_lines else (stderr.strip()[:200] or "Analysis failed")
            logger.error(f"❌ [{shortcode}] Analysis failed: {error_detail}")
            logger.debug(f"[{shortcode}] stdout tail:\n{stdout[-800:]}")
            raise HTTPException(
                status_code=400,
                detail=error_detail
            )

        logger.info(f"✅ [{shortcode}] Analysis complete! Fetching from database...")

        # Get result from database — retry up to 4 times in case the SQLite write
        # hasn't flushed yet (race condition between subprocess write and our read).
        analysis = None
        for _attempt in range(4):
            analysis = db.check_cache(shortcode)
            if analysis:
                if _attempt > 0:
                    logger.info(f"🔄 [{shortcode}] Found in database on retry {_attempt}")
                break
            if _attempt < 3:
                logger.warning(f"⏳ [{shortcode}] Not in DB yet (attempt {_attempt+1}/4), retrying in 1s…")
                await asyncio.sleep(1)

        if not analysis:
            logger.error(f"❌ [{shortcode}] Not found in database after 4 attempts!")
            raise HTTPException(
                status_code=500,
                detail="Analysis completed but result not found in database"
            )

        # Filter response
        filtered_data = {
            'url': analysis.get('url', ''),
            'username': analysis.get('username', ''),
            'content_type': analysis.get('content_type', content_type),
            'thumbnail': analysis.get('thumbnail', ''),
            'title': analysis.get('title', ''),
            'summary': analysis.get('summary', ''),
            'tags': analysis.get('tags', []),
            'music': analysis.get('music', ''),
            'category': analysis.get('category', ''),
            'needs_review': analysis.get('needs_review', False)
        }

        db.remove_from_queue(shortcode)
        logger.info(f"🔓 [{shortcode}] Released from processing queue")

        return {"status": "ran", "data": filtered_data}

    except asyncio.TimeoutError:
        logger.error(f"❌ [{shortcode}] Analysis reached {ANALYSIS_SUBPROCESS_TIMEOUT}s timeout. Forcing termination.")
        with _active_processes_lock:
            proc = _active_processes.pop(shortcode, None)
        if proc:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass
        db.remove_from_queue(shortcode)
        raise HTTPException(
            status_code=504,
            detail="Analysis timed out. The process took longer than the 10-minute allowed maximum."
        )
    except HTTPException as he:
        # Don't remove from queue for 202 (retry-queued) — the item was
        # intentionally kept in the retry queue by main.py.
        if he.status_code != 202:
            db.remove_from_queue(shortcode)
        raise
    except subprocess.SubprocessError as e:
        logger.error(f"❌ [{shortcode}] Subprocess error: {str(e)}")
        db.remove_from_queue(shortcode)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    except Exception as e:
        logger.error(f"❌ [{shortcode}] Unexpected error: {str(e)}")
        db.remove_from_queue(shortcode)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_instagram(request: AnalyzeRequest, token: str = Depends(verify_token)):
    """
    Analyze content from URL (Instagram, YouTube, or web page)

    - Checks cache first for instant retrieval
    - If not cached, adds to processing queue
    - Handles multiple concurrent requests with queuing
    - Returns comprehensive summary with title, tags, music, category
    """
    start_time = datetime.now()

    # Detect content type and extract primary key
    try:
        url_str = str(request.url)
        validation = validate_link(url_str)
        if not validation['valid']:
            raise ValueError(validation['error'])
        shortcode    = validation['shortcode']
        content_type = validation['content_type']
        # Use the normalised URL (e.g. canonical YouTube URL)
        url_str = validation['url']
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {str(e)}")
    
    logger.info(f"📥 New request: {shortcode}")
    
    # Initialize database connection
    db = get_db()
    
    try:
        # Step 1: Check database cache first
        logger.info(f"🔍 [{shortcode}] Checking database cache...")
        cached_result = db.check_cache(shortcode)
        
        if cached_result:
            # Force re-analyze: hard-delete existing record and proceed with fresh analysis
            if request.force:
                logger.info(f"🔄 [{shortcode}] Force re-analyze requested — clearing cached data")
                db.hard_delete_post(shortcode)
                cached_result = None  # fall through to fresh analysis
            # Soft-deleted posts stay deleted on a bare resubmission — restoring
            # requires explicit intent (request.restore=True) so an automated
            # import/sync script re-encountering the same URL can't silently
            # undo a user's delete. See restore_post() in database.py.
            elif cached_result.get('is_hidden') == 1:
                if request.restore:
                    db.restore_post(shortcode)
                    cached_result['is_hidden'] = 0
                    logger.info(f"♻️ [{shortcode}] Restored from soft-delete (restore=true). Returning cached data.")
                else:
                    logger.info(f"🚫 [{shortcode}] Post is soft-deleted — resubmission ignored (pass restore=true to bring it back)")
                    raise HTTPException(
                        status_code=410,
                        detail=f"Post {shortcode} was deleted. Resubmit with restore=true to restore it, or force=true to re-analyze from scratch."
                    )
            else:
                logger.info(f"⚡ [{shortcode}] Found in cache! Returning instantly.")

        if cached_result:
            # Filter response
            filtered_data = {
                'url': cached_result.get('url', ''),
                'username': cached_result.get('username', ''),
                'content_type': cached_result.get('content_type', content_type),
                'thumbnail': cached_result.get('thumbnail', ''),
                'title': cached_result.get('title', ''),
                'summary': cached_result.get('summary', ''),
                'tags': cached_result.get('tags', []),
                'music': cached_result.get('music', ''),
                'category': cached_result.get('category', ''),
                'needs_review': cached_result.get('needs_review', False)
            }
            
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ [{shortcode}] Response sent ({processing_time:.2f}s)")
            
            return AnalysisResponse(
                success=True,
                cached=True,
                data=filtered_data,
                processing_time=processing_time
            )
        
        # Step 2: Not in cache — run inline if a slot is free, otherwise
        # queue automatically (the background queue_worker picks it up).
        logger.info(f"💾 [{shortcode}] Not in cache")

        outcome = await _run_or_queue_analysis(
            shortcode, url_str, content_type, request.caption, request.hashtags, request.date_saved, run_inline=True
        )
        if outcome["status"] == "queued":
            raise HTTPException(
                status_code=503,
                detail=f"Server busy analyzing 1 post. Your request is queued (position: {outcome['position']}). It will be processed automatically. Check back in a few minutes."
            )

        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ [{shortcode}] Response sent ({processing_time:.2f}s total)")

        return AnalysisResponse(
            success=True,
            cached=False,
            data=outcome["data"],
            processing_time=processing_time
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [{shortcode}] Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


def _run_rescan_subprocess(args: list, timeout: int = None) -> tuple:
    """Run scripts/rescan_post.py with the given argv (after the script
    path), streaming its stdout live to the logger line-by-line as it runs
    (rather than only reporting the full output after the fact — that was
    the entire reason a 100+-reel rescan looked totally silent in the
    console for its whole duration), and return (returncode, stdout, stderr).
    Blocking — callers on the single-item sync path use asyncio.to_thread()
    with `timeout` set; the --batch background path (no HTTP caller waiting)
    calls this directly with timeout=None from inside its own daemon thread.

    PYTHONUNBUFFERED=1 is required here: without it, a child Python process
    whose stdout is a pipe (not a TTY) block-buffers, so rescan_post.py's
    own print() progress lines wouldn't actually reach this pipe until the
    buffer filled or the process exited — defeating the whole point of
    streaming.
    """
    cmd = [sys.executable, "scripts/rescan_post.py"] + args
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        cwd=str(Path(__file__).parent),
        bufsize=1,
    )
    lines = []
    start = time.monotonic()
    try:
        for line in proc.stdout:
            lines.append(line)
            stripped = line.rstrip()
            if stripped:
                logger.info(f"[rescan] {stripped}")
            if timeout is not None and (time.monotonic() - start) > timeout:
                proc.kill()
                proc.wait()
                return None, "".join(lines), f"rescan_post.py timed out after {timeout}s"
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return None, "".join(lines), f"rescan_post.py timed out after {timeout}s"
    return proc.returncode, "".join(lines), proc.stderr.read()


def _spawn_rescan_batch_background(shortcodes: list):
    """Fire-and-forget scripts/rescan_post.py --batch <shortcodes> — used by
    the multi-shortcode branch below so the HTTP response never blocks on a
    whole version cohort's worth of work."""
    def _run():
        try:
            returncode, stdout, stderr = _run_rescan_subprocess(["--batch", ",".join(shortcodes)])
            if returncode != 0:
                logger.error(f"❌ [rescan-batch] --batch subprocess exited {returncode}: "
                             f"{(stderr or stdout or '')[-500:]}")
        except Exception as e:
            logger.error(f"❌ [rescan-batch] --batch subprocess crashed: {e}")
        finally:
            # Safety net: scripts/rescan_post.py --batch removes each
            # shortcode from processing_queue as it finishes one, but if the
            # subprocess dies before reaching one, don't leave it stuck at
            # status='processing' forever.
            db = get_db()
            still_processing = set(db.get_processing())  # already a list of shortcodes, not rows
            for sc in shortcodes:
                if sc in still_processing:
                    db.remove_from_queue(sc)

    threading.Thread(target=_run, daemon=True).start()


@app.post("/reanalyze/bulk", response_model=BulkReanalyzeResponse)
async def reanalyze_bulk(request: BulkReanalyzeRequest, token: str = Depends(verify_token)):
    """
    Rescan one or many posts — the version-gap-aware, non-destructive rescan
    pipeline (see "Rescan pipeline" in backend/CLAUDE.md and
    scripts/rescan_post.py). Deliberately separate from first-time analysis:
    never touches main.py or core/batch_processor.py, and never deletes a
    row before a replacement is ready — every write goes through
    db.save_analysis()'s existing upsert, so a rescan that fails partway
    (Instagram content genuinely gone, an expired OpenAI batch request)
    always leaves the original row exactly as it was.

    For each shortcode:
    - Not found -> `errors`.
    - Stamped exactly version 7 (the one version whose gap to current is
      purely the importance-scoring rubric fix) -> cheap, synchronous,
      no-redownload fix via core.importance.score_and_stamp_importance ->
      `rescored`.
    - A single non-cheap shortcode -> spawn `scripts/rescan_post.py
      <shortcode>` and AWAIT it (bounded by RESCAN_SUBPROCESS_TIMEOUT) —
      individual rescans are always synchronous, so the caller gets an
      immediate result -> `rescored` on success, `errors` on failure/timeout
      (the row is never touched on a failure path, so there's nothing to
      clean up).
    - Multiple non-cheap shortcodes -> marked `processing` (the existing
      generic queue primitive, for GET /queue-status visibility) and handed
      to `scripts/rescan_post.py --batch <shortcodes>` as a background,
      un-awaited subprocess -> `queued`. Progress is polled via
      GET /queue-status (`currently_processing` while local analyzer steps
      run, then `rescan_batch_pending` once submitted to OpenAI under
      ANALYSIS_MODE=batch).
    """
    db = get_db()
    rescored: List[str] = []
    queued: List[str] = []
    errors: List[BulkReanalyzeError] = []

    cheap, full = [], []
    for shortcode in request.shortcodes:
        row = db.check_cache(shortcode)
        if not row:
            errors.append(BulkReanalyzeError(shortcode=shortcode, error="Post not found"))
            continue
        if row.get("analysis_version") == 7:
            cheap.append((shortcode, row))
        else:
            full.append(shortcode)

    for shortcode, row in cheap:
        importance = score_and_stamp_importance(
            db, shortcode, row.get("title"), row.get("summary"),
            row.get("tags"), row.get("category"), row.get("username"),
        )
        if importance is None:
            errors.append(BulkReanalyzeError(
                shortcode=shortcode, error="No parseable importance score returned"
            ))
        else:
            rescored.append(shortcode)

    if len(full) == 1:
        shortcode = full[0]
        returncode, stdout, stderr = await asyncio.to_thread(
            _run_rescan_subprocess, [shortcode], RESCAN_SUBPROCESS_TIMEOUT
        )
        if returncode == 0:
            rescored.append(shortcode)
        elif returncode == 2:
            errors.append(BulkReanalyzeError(
                shortcode=shortcode,
                error="Rate-limited by Instagram — automatically queued for retry in 24h; existing data untouched",
            ))
        else:
            tail = (stderr or stdout or "").strip()[-300:]
            reason = f"timed out after {RESCAN_SUBPROCESS_TIMEOUT}s" if returncode is None else f"failed ({tail})"
            errors.append(BulkReanalyzeError(
                shortcode=shortcode, error=f"Rescan {reason}; existing data untouched",
            ))
    elif full:
        for shortcode in full:
            row = db.check_cache(shortcode)
            db.mark_processing(shortcode, row.get("url"), row.get("content_type", "instagram"))
        _spawn_rescan_batch_background(full)
        queued.extend(full)

    return BulkReanalyzeResponse(success=True, rescored=rescored, queued=queued, errors=errors)


@app.get("/cache/{shortcode}")
async def check_cache(shortcode: str, token: str = Depends(verify_token)):
    """
    Check if Instagram post is already analyzed and cached
    
    - Returns cached analysis if available
    - Returns 404 if not found
    - Requires API authentication
    """
    try:
        db = get_db()
        result = db.check_cache(shortcode)
        
        if not result:
            raise HTTPException(status_code=404, detail="Not found in cache")
        
        # Filter response to only include essential fields
        filtered_data = {
            'url': result.get('url', ''),
            'username': result.get('username', ''),
            'title': result.get('title', ''),
            'summary': result.get('summary', ''),
            'tags': result.get('tags', []),
            'music': result.get('music', ''),
            'category': result.get('category', ''),
            'needs_review': result.get('needs_review', False)
        }
        
        return {
            "success": True,
            "cached": True,
            "data": filtered_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recent")
async def get_recent_analyses(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="recent", pattern="^(recent|importance|date_saved|post_date)$"),
    token: str = Depends(verify_token),
):
    """
    Get recent analyses from database (lightweight — no analysis blobs)

    - Returns most recently analyzed content with UI-essential fields only
    - Supports pagination via offset
    - sort=recent (default): most recently analyzed first
    - sort=importance: highest importance score first (unscored posts last),
      analyzed_at as tie-breaker — see core/importance.py
    - sort=date_saved: real Instagram save date (oldest first), then
      analyzed_at for posts outside the backfill — see
      scripts/backfill_date_saved.py
    - sort=post_date: the content's own publish date (oldest first), same
      analyzed_at fallback — a distinct axis from date_saved ("when was
      this posted" vs. "when did I save it")
    - Default limit: 50, max: 1000
    - Requires API authentication
    """
    try:
        db = get_db()
        results = db.get_recent_light(limit=limit, offset=offset, sort=sort)
        total = db.get_total_count()

        return {
            "success": True,
            "count": len(results),
            "total": total,
            "offset": offset,
            "data": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sync")
async def sync_posts(
    since: str = Query(..., description="ISO timestamp — return posts updated after this time"),
    limit: int = Query(default=500, ge=1, le=1000),
    token: str = Depends(verify_token),
):
    """
    Delta sync endpoint — returns posts modified after the given timestamp.
    Used by the mobile app to incrementally update its local SQLite database.
    Only returns lightweight fields (no analysis blobs).
    """
    try:
        db = get_db()
        results = db.get_posts_since(since, limit=limit)

        return {
            "success": True,
            "count": len(results),
            "since": since,
            "data": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sync/deleted")
async def sync_deleted(
    since: str = Query(..., description="ISO timestamp — return posts deleted after this time"),
    token: str = Depends(verify_token),
):
    """
    Returns shortcodes of posts that were soft-deleted after the given timestamp.
    The mobile app uses this to remove posts from its local database.
    """
    try:
        db = get_db()
        results = db.get_deleted_since(since)

        return {
            "success": True,
            "count": len(results),
            "since": since,
            "data": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_database_stats(token: str = Depends(verify_token)):
    """
    Get database statistics
    
    - Total documents
    - Storage usage
    - Category breakdown
    - Capacity information
    - Requires API authentication
    """
    try:
        db = get_db()
        stats = db.get_stats()
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/categories")
async def get_all_categories(token: str = Depends(verify_token)):
    """
    Get all categories with post counts
    - Requires API authentication
    """
    try:
        db = get_db()
        stats = db.get_stats()
        category_counts = stats.get('categories', {})
        
        # Convert to list format with icons
        categories = []
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            categories.append({
                'id': cat.lower(),
                'name': cat,
                'count': count
            })
        
        return {
            "success": True,
            "categories": categories,
            # The full canonical taxonomy (core/categories.py), independent of
            # which categories currently have posts — lets clients offer every
            # valid label (e.g. in a category-editing dropdown) instead of
            # only ones already in use.
            "canonical": CATEGORIES,
            "total": sum(c['count'] for c in categories)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/changelog")
async def get_changelog(token: str = Depends(verify_token)):
    """
    Get the analysis pipeline/taxonomy changelog (newest version first),
    e.g. when categories were added or the pipeline changed in a way that
    makes older posts worth re-reviewing. See CURRENT_ANALYSIS_VERSION in
    core/database.py.
    - Requires API authentication
    """
    try:
        db = get_db()
        history = db.get_changelog()

        return {
            "success": True,
            "current_version": history[0]['version'] if history else None,
            "history": history
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/category/{category}")
async def get_by_category(
    category: str,
    limit: int = Query(default=20, ge=1, le=100),
    token: str = Depends(verify_token)
):
    """
    Get analyses by category

    See GET /categories for the current list of valid category labels.
    - Requires API authentication
    """
    try:
        db = get_db()
        results = db.get_by_category(category, limit=limit)
        
        return {
            "success": True,
            "category": category,
            "count": len(results),
            "data": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
async def search_by_tags(
    tags: str = Query(..., description="Comma-separated tags to search"),
    limit: int = Query(default=20, ge=1, le=100),
    token: str = Depends(verify_token)
):
    """
    Search analyses by tags
    
    - Provide comma-separated tags
    - Example: travel,sikkim,budget
    - Requires API authentication
    """
    try:
        tag_list = [tag.strip() for tag in tags.split(',')]
        
        db = get_db()
        results = db.search_tags(tag_list, limit=limit)
        
        return {
            "success": True,
            "tags": tag_list,
            "count": len(results),
            "data": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search/semantic")
async def search_semantic(
    q: str = Query(..., description="Free-text topic/query to search for"),
    limit: int = Query(default=20, ge=1, le=100),
    min_similarity: float = Query(default=0.0, ge=0.0, le=1.0, description="Drop results below this cosine similarity"),
    token: str = Depends(verify_token),
    x_client_env: Optional[str] = Header(default=None, description="'dev' from a local `next dev` session; omitted/anything else counts as real usage")
):
    """
    Semantic search over analyzed posts by meaning, not just keyword overlap.
    Embeds the query with the same model used at analysis time
    (OpenAI text-embedding-3-small) and ranks stored posts by cosine
    similarity, computed in-process with numpy (no vector-search extension —
    unnecessary at this dataset's scale).

    Posts analyzed before embedding generation existed (or analyzed without
    an OPENAI_API_KEY configured) won't have an embedding and are excluded
    from results — run scripts/backfill_embeddings.py to fill those in.

    Requires API authentication.
    """
    try:
        router = get_router()
        db = get_db()

        # Reuse a prior embedding for the same normalized query text if one
        # exists (the `embeddings` table doubles as an embedding cache — see
        # get_cached_query_embedding) rather than re-calling the embedding
        # API for a repeated search (e.g. the /space search box resubmitting
        # the same term).
        query_embedding = db.get_cached_query_embedding(q)
        if not query_embedding:
            query_embedding = await asyncio.to_thread(router.generate_embedding, q)
        if not query_embedding:
            raise HTTPException(
                status_code=503,
                detail="Could not generate a query embedding — check OPENAI_API_KEY in backend/config/.api_keys."
            )

        try:
            db.log_search_query(q, query_embedding, source="search", client_env=resolve_client_env(x_client_env))
        except Exception as e:
            logger.warning(f"Failed to log search query: {e}")

        stored = db.get_all_embeddings()
        if not stored:
            return {"success": True, "query": q, "count": 0, "data": []}

        top = rag.rank_by_embedding(query_embedding, stored, limit=limit, min_similarity=min_similarity)

        results = []
        for similarity, shortcode in top:
            post = db.check_cache(shortcode)
            if not post:
                continue
            results.append({
                "shortcode": shortcode,
                "similarity": round(similarity, 4),
                "url": post.get("url", ""),
                "username": post.get("username", ""),
                "title": post.get("title", ""),
                "summary": post.get("summary", ""),
                "tags": post.get("tags", []),
                "category": post.get("category", ""),
                "thumbnail": post.get("thumbnail", ""),
            })

        return {"success": True, "query": q, "count": len(results), "data": results}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChatThreadCreate(BaseModel):
    title: Optional[str] = None


class ChatMessageCreate(BaseModel):
    message: str


@app.post("/chat/threads")
async def create_chat_thread(req: ChatThreadCreate = Body(default=ChatThreadCreate()), token: str = Depends(verify_token)):
    """
    Create a new RAG chatbot conversation thread.
    Requires API authentication.
    """
    try:
        db = get_db()
        thread = db.create_chat_thread(title=req.title)
        if not thread:
            raise HTTPException(status_code=500, detail="Could not create chat thread.")
        return {"success": True, "data": thread}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/threads")
async def list_chat_threads(token: str = Depends(verify_token)):
    """
    List all RAG chatbot conversation threads, most-recently-updated first.
    Requires API authentication.
    """
    try:
        db = get_db()
        threads = db.list_chat_threads()
        return {"success": True, "count": len(threads), "data": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/threads/{thread_id}")
async def get_chat_thread(thread_id: str, token: str = Depends(verify_token)):
    """
    Return a chat thread and its full message history.
    Requires API authentication.
    """
    try:
        db = get_db()
        thread = db.get_chat_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Chat thread not found.")
        messages = db.get_chat_messages(thread_id)
        return {"success": True, "data": {**thread, "messages": messages}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/threads/{thread_id}/messages")
async def send_chat_message(
    thread_id: str,
    req: ChatMessageCreate,
    token: str = Depends(verify_token),
    x_client_env: Optional[str] = Header(default=None, description="'dev' from a local `next dev` session; omitted/anything else counts as real usage")
):
    """
    Ask the RAG chatbot a question within a thread.

    Retrieves the saved posts most relevant to the question (same embeddings
    used by GET /search/semantic), asks the chat-task LLM (core/model_router.py's
    generate_chat_text — Gemini -> OpenAI[dedicated OPENAI_CHAT_API_KEY] ->
    local Ollama) to answer from that content plus recent thread history,
    persists both the user message and the assistant reply, and returns both.

    Requires API authentication.
    """
    try:
        db = get_db()
        thread = db.get_chat_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Chat thread not found.")

        question = req.message.strip()
        if not question:
            raise HTTPException(status_code=400, detail="message must not be empty.")

        router = get_router()

        try:
            answer, sources, query_embedding = await asyncio.to_thread(rag.answer_question, router, db, thread_id, question)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

        try:
            db.log_search_query(question, query_embedding, source="chat", client_env=resolve_client_env(x_client_env))
        except Exception as e:
            logger.warning(f"Failed to log chat query: {e}")

        user_message = db.add_chat_message(thread_id, "user", question)
        assistant_message = db.add_chat_message(thread_id, "assistant", answer, sources=sources)
        db.touch_chat_thread(thread_id, title=question[:80])

        return {"success": True, "data": {"user_message": user_message, "assistant_message": assistant_message}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chat/threads/{thread_id}")
async def delete_chat_thread(thread_id: str, token: str = Depends(verify_token)):
    """
    Delete a chat thread and its messages.
    Requires API authentication.
    """
    try:
        db = get_db()
        deleted = db.delete_chat_thread(thread_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Chat thread not found.")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StudyGuideCreate(BaseModel):
    shortcodes: List[str]
    # What this was generated from, freeform but with a recognizable prefix
    # ("Board: ...", "Search: ...", "Theme/Idea/Cluster: ...", "3D space
    # selection") stamped by every superbrain-web caller — the only
    # source-of-truth for "what kind of thing" a collection is (a separate
    # machine-readable source_type field was tried and removed: every
    # caller that would set it also sets this label with a parseable
    # prefix, so it never carried information the label didn't).
    # superbrain-web's /study-guides corkboard parses this prefix to
    # color-code each pile (src/lib/studyGuideSource.ts).
    source_label: Optional[str] = None
    # Optional semantic sub-groups (e.g. a theme's micro-clusters, each a
    # list of shortcodes) for the >MAX_STUDY_GUIDE_POSTS chunking pipeline
    # to pack chunks along — see core/study_guide.py's chunk_posts(). Falls
    # back to even positional chunking when omitted (a plain selection/
    # search result has no known sub-structure).
    groups: Optional[List[List[str]]] = None


def _run_study_guide_pipeline(db, router, posts, groups, source_label, collection_id):
    """Runs core/study_guide.py's pipeline in a background thread (started
    by POST /study-guide, below) and persists each guide the moment it's
    generated, not batched until the whole pipeline finishes — see
    generate_study_guide_pipeline()'s docstring for why: a crash/restart
    mid-run should only lose whatever guide was actively in flight, not
    every guide already completed. Marks the collection 'complete' or
    'failed' on the way out; guides already saved before a failure are left
    in place either way.
    """
    def on_guide(g):
        db.create_study_guide(
            title=g["title"],
            content=g["content"],
            shortcodes=g["shortcodes"],
            excluded_shortcodes=g["excluded_shortcodes"],
            source_label=source_label,
            collection_id=collection_id,
            role=g["role"],
            position=g["position"],
            model=g.get("model"),
        )

    try:
        study_guide.generate_study_guide_pipeline(router, posts, groups, on_guide=on_guide)
        db.update_study_guide_collection_status(collection_id, "complete")
    except Exception as e:
        logger.warning(f"Study guide pipeline failed for collection {collection_id}: {e}")
        db.update_study_guide_collection_status(collection_id, "failed", error=str(e))


@app.post("/study-guide")
async def create_study_guide(
    req: StudyGuideCreate,
    token: str = Depends(verify_token),
    x_client_env: Optional[str] = Header(default=None, description="'dev' from a local `next dev` session; omitted/anything else counts as real usage")
):
    """
    Kick off an on-demand study-guide "collection" distilling a user-picked
    set of posts (a selection, search result, or theme/cluster from
    superbrain-web) into one or more markdown docs — see core/study_guide.py
    for the full pipeline.

    Returns IMMEDIATELY with the (initially empty) collection — the actual
    LLM pipeline runs in a background thread (_run_study_guide_pipeline,
    above), so the caller never has to hold a connection open for however
    long generation takes (potentially several minutes for a large,
    multi-call request). Poll GET /study-guide-collections/{id} to watch
    `status` ('generating' -> 'complete'/'failed') and `guides` fill in —
    each guide is persisted the instant it's generated, not all at once at
    the end.

    At or under MAX_STUDY_GUIDE_POSTS this is one LLM call and one saved
    guide. Above it, by explicit user request, the pipeline runs BOTH a
    whole-selection pass and a chunked-then-merged pass and reconciles them
    into a final guide — every intermediate guide (full/merge/chunk) is
    persisted alongside the final one as siblings in the same collection,
    none are deleted. Every call is pinned to OpenAI's STUDY_GUIDE_MODEL
    specifically (no Groq/Gemini/OpenRouter/Ollama fallback) — also an
    explicit product decision, not a technical necessity.

    Requires API authentication.
    """
    try:
        shortcodes = list(dict.fromkeys(s for s in req.shortcodes if s))
        if not shortcodes:
            raise HTTPException(status_code=400, detail="shortcodes must not be empty.")
        if len(shortcodes) > study_guide.ABSOLUTE_MAX_STUDY_GUIDE_POSTS:
            raise HTTPException(
                status_code=400,
                detail=f"Too many posts selected ({len(shortcodes)}) — the absolute limit is "
                       f"{study_guide.ABSOLUTE_MAX_STUDY_GUIDE_POSTS} per generation."
            )
        db = get_db()
        posts = db.get_posts_by_shortcodes(shortcodes)
        if not posts:
            raise HTTPException(status_code=404, detail="None of the given shortcodes were found.")

        try:
            count = study_guide.expected_guide_count(posts, req.groups)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        collection = db.create_study_guide_collection(
            source_label=req.source_label, status="generating", expected_guide_count=count
        )
        if not collection:
            raise HTTPException(status_code=500, detail="Could not create the study guide collection.")

        # Choosing a post as study-guide source material is a real but
        # WEAKER interest signal than actually watching it — record it
        # separately (reels_study_guide), never into post_views, so the Home
        # recommendation engine (superbrain-web/src/lib/recommendations.ts)
        # can keep real qualifying views ranked above it. Best-effort and
        # must never block generation from starting.
        db.record_study_guide_reels(collection["id"], shortcodes, client_env=resolve_client_env(x_client_env))

        router = get_router()
        threading.Thread(
            target=_run_study_guide_pipeline,
            args=(db, router, posts, req.groups, req.source_label, collection["id"]),
            daemon=True,
        ).start()

        return {"success": True, "data": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guides")
async def list_study_guides(token: str = Depends(verify_token)):
    """
    List all saved study guides across every collection, newest first.

    Requires API authentication.
    """
    try:
        db = get_db()
        guides = db.get_study_guides()
        return {"success": True, "count": len(guides), "data": guides}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guides/{study_guide_id}")
async def get_study_guide(study_guide_id: int, token: str = Depends(verify_token)):
    """
    Return a single saved study guide.

    Requires API authentication.
    """
    try:
        db = get_db()
        guide = db.get_study_guide(study_guide_id)
        if not guide:
            raise HTTPException(status_code=404, detail="Study guide not found.")
        return {"success": True, "data": guide}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/study-guides/{study_guide_id}")
async def delete_study_guide(study_guide_id: int, token: str = Depends(verify_token)):
    """
    Delete a single saved study guide (not its collection or siblings).

    Requires API authentication.
    """
    try:
        db = get_db()
        if not db.delete_study_guide(study_guide_id):
            raise HTTPException(status_code=404, detail="Study guide not found.")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guides/{study_guide_id}/pdf")
async def get_study_guide_pdf(study_guide_id: int, token: str = Depends(verify_token)):
    """
    Render a saved study guide's markdown content as a PDF, on demand (see
    core/study_guide_pdf.py — nothing is persisted to disk, always rendered
    fresh from the stored content).

    Requires API authentication.
    """
    try:
        db = get_db()
        guide = db.get_study_guide(study_guide_id)
        if not guide:
            raise HTTPException(status_code=404, detail="Study guide not found.")
        pdf_bytes = await asyncio.to_thread(
            study_guide_pdf.render_study_guide_pdf, guide.get("title") or "Study Guide", guide["content"]
        )
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', guide.get("title") or f"study-guide-{study_guide_id}")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{safe_name}.pdf"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guides/{study_guide_id}/thumbnail")
async def get_study_guide_thumbnail(study_guide_id: int, token: str = Depends(verify_token)):
    """
    Rasterize the first page of a saved study guide's PDF as a PNG — used by
    superbrain-web's collection view for a thumbnail grid. Rendered once per
    guide content and then served from the on-disk cache (see
    core/study_guide_pdf.py's get_cached_study_guide_thumbnail).

    Requires API authentication.
    """
    try:
        db = get_db()
        guide = db.get_study_guide(study_guide_id)
        if not guide:
            raise HTTPException(status_code=404, detail="Study guide not found.")
        png_bytes = await asyncio.to_thread(
            study_guide_pdf.get_cached_study_guide_thumbnail,
            study_guide_id,
            guide.get("title") or "Study Guide",
            guide["content"],
        )
        return Response(content=png_bytes, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guide-collections")
async def list_study_guide_collections(token: str = Depends(verify_token)):
    """
    List all study guide collections, newest first, each with its member
    guides attached (ordered: final, full, merge, then individual chunks).

    Requires API authentication.
    """
    try:
        db = get_db()
        collections = db.get_study_guide_collections()
        return {"success": True, "count": len(collections), "data": collections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guide-collections/{collection_id}")
async def get_study_guide_collection(collection_id: int, token: str = Depends(verify_token)):
    """
    Return a single study guide collection with its member guides attached.

    Requires API authentication.
    """
    try:
        db = get_db()
        collection = db.get_study_guide_collection(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Study guide collection not found.")
        return {"success": True, "data": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/study-guide-collections/{collection_id}")
async def delete_study_guide_collection(collection_id: int, token: str = Depends(verify_token)):
    """
    Delete a study guide collection and every guide in it.

    Requires API authentication.
    """
    try:
        db = get_db()
        if not db.delete_study_guide_collection(collection_id):
            raise HTTPException(status_code=404, detail="Study guide collection not found.")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/study-guide-collections/{collection_id}/opened")
async def mark_study_guide_collection_opened(collection_id: int, token: str = Depends(verify_token)):
    """
    Stamp this collection's last_opened_at — fired by superbrain-web's
    /study-guides/[id] page every time a guide within it is actually
    opened. Feeds the Home recommendation engine's reels_study_guide signal
    (see GET /study-guide-reel-history) alongside how long ago the
    collection was generated: reopening an old study guide nudges its
    source reels' recommendation weight back up, the same way rewatching a
    post does for a real view.

    Fire-and-forget from the frontend — failures here should never surface
    to the user, so this returns success:false rather than raising where
    reasonable.

    Requires API authentication.
    """
    try:
        db = get_db()
        ok = db.mark_study_guide_collection_opened(collection_id)
        return {"success": ok}
    except Exception as e:
        logger.error(f"Error marking study guide collection opened: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ping")
async def ping():
    """Ultra-lightweight liveness check — no DB, no auth, instant response."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/status")
async def status():
    """
    Server status check - no auth required.
    """
    return {
        "status": "online",
        "version": "2.0.0",
        "message": "Server is running. Configure app with server URL and Access Token from token.txt."
    }


@app.get("/connect-info")
async def connect_info(request: Request):
    """
    Returns connection details for QR code scanning.
    No auth required — used by the mobile app to auto-fill settings.
    The URL is built from the request so it matches whatever address the client used.
    """
    # Build the base URL from the incoming request
    scheme = request.headers.get('x-forwarded-proto', request.url.scheme)
    host = request.headers.get('x-forwarded-host', request.headers.get('host', 'localhost:5050'))
    base_url = f"{scheme}://{host}"

    return {
        "url": base_url,
        "token": API_TOKEN,
        "version": "2.0.0",
        "name": "SuperBrain"
    }


@app.get("/analysis-status/{shortcode}")
async def analysis_status(shortcode: str, token: str = Depends(verify_token)):
    """
    Check if a post has been analyzed yet.
    Returns status: 'complete', 'processing', 'queued', or 'not_found'.
    Used by the app to poll for completion after sharing a URL.
    """
    try:
        db = get_db()

        # Check if fully analyzed
        cached = db.check_cache(shortcode)
        if cached:
            return {
                "status": "complete",
                "shortcode": shortcode,
                "title": cached.get('title', ''),
                "category": cached.get('category', ''),
                "data": {
                    'title': cached.get('title', ''),
                    'summary': cached.get('summary', ''),
                    'tags': cached.get('tags', []),
                    'category': cached.get('category', ''),
                    'content_type': cached.get('content_type', ''),
                    'thumbnail': cached.get('thumbnail', ''),
                }
            }

        # Check if currently processing
        processing = db.get_processing()
        if shortcode in processing:
            return {"status": "processing", "shortcode": shortcode}

        # Check if in queue
        queue = db.get_queue()
        for i, item in enumerate(queue):
            if item['shortcode'] == shortcode:
                return {"status": "queued", "shortcode": shortcode, "position": i + 1}

        return {"status": "not_found", "shortcode": shortcode}

    except Exception as e:
        logger.error(f"Error checking analysis status for {shortcode}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ConnectRequest(BaseModel):
    """Request model for deprecated /connect endpoint."""
    api_key: Optional[str] = None


@app.post("/connect")
async def connect(request: ConnectRequest):
    """
    Deprecated endpoint kept for backward compatibility.
    Use direct Server URL + API key configuration in app settings.
    """
    raise HTTPException(
        status_code=410,
        detail="Deprecated. Configure Server URL and Access Token directly in app Settings."
    )


# ─────────────────────────────────────────────────────────────────
# Collections endpoints
# ──────────────────────────────────────────────────────────────────

class CollectionUpsertRequest(BaseModel):
    id: str
    name: str
    icon: str = "📁"
    post_ids: List[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CollectionPostsRequest(BaseModel):
    post_ids: List[str]


# Allowed fields for import validation
ALLOWED_POST_FIELDS = {
    'shortcode', 'url', 'username', 'content_type', 'post_date',
    'likes', 'thumbnail', 'title', 'summary', 'tags', 'music', 'category',
    'visual_analysis', 'audio_transcription', 'text_analysis', 'analysis_version',
    'language', 'media_files', 'enjoyment_rating', 'perceived_importance_rating',
    'should_revisit'
}

# Manual rating axes (distinct from the AI-scored `importance` column) —
# Netflix-style tri-state: null (default) | 'liked' | 'loved'.
RATING_VALUES = {None, 'liked', 'loved'}


def resolve_client_env(x_client_env: Optional[str]) -> str:
    """Normalizes the optional `X-Client-Env` header used to tag
    post_views/search_queries rows as 'dev' or 'prod' — see the client_env
    migrations in core/database.py for the full rationale. Anything other
    than the literal string 'dev' (missing header, unrecognized value, the
    iOS app which has no dev/prod build distinction and never sends this)
    normalizes to 'prod', so a bug here fails toward *counting* a view/search
    as real rather than silently excluding real usage."""
    return "dev" if x_client_env == "dev" else "prod"

class ImportData(BaseModel):
    version: Optional[str] = None
    posts: List[dict] = []
    collections: List[dict] = []


@app.get("/collections")
async def get_collections(token: str = Depends(verify_token)):
    """Return all collections stored on the server."""
    try:
        db = get_db()
        return {"success": True, "data": db.get_collections()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections")
async def upsert_collection(req: CollectionUpsertRequest, token: str = Depends(verify_token)):
    """Create or fully replace a collection (upsert by id)."""
    try:
        db = get_db()
        saved = db.upsert_collection(
            req.id, req.name, req.icon, req.post_ids,
            req.created_at, req.updated_at
        )
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=500, detail="Failed to save collection")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/collections/{collection_id}/posts")
async def update_collection_posts(collection_id: str, req: CollectionPostsRequest,
                                   token: str = Depends(verify_token)):
    """Replace the post_ids list for a collection."""
    try:
        db = get_db()
        ok = db.update_collection_posts(collection_id, req.post_ids)
        if ok:
            return {"success": True, "data": db.get_collection(collection_id)}
        raise HTTPException(status_code=404, detail="Collection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str, token: str = Depends(verify_token)):
    """Delete a collection by id. The default Watch Later cannot be deleted."""
    if collection_id == "default_watch_later":
        raise HTTPException(status_code=403, detail="Cannot delete the default Watch Later collection")
    try:
        db = get_db()
        ok = db.delete_collection(collection_id)
        if ok:
            return {"success": True, "message": "Collection deleted"}
        raise HTTPException(status_code=404, detail="Collection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────
# Boards endpoints — user-curated collections created from
# superbrain-web's /boards page. See core/database.py's schema comment
# above `boards`/`board_subcollections` for how this differs from the
# Instagram-import-driven Collections above.
# ─────────────────────────────────────────────────────────────────

class BoardCreateRequest(BaseModel):
    name: str
    icon: str = "🗂️"


class BoardUpdateRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None


class SubcollectionCreateRequest(BaseModel):
    name: str
    icon: str = "📁"


@app.get("/boards")
async def get_boards(token: str = Depends(verify_token)):
    """Return all boards, each with its subcollections attached."""
    try:
        db = get_db()
        return {"success": True, "data": db.get_boards()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/boards")
async def create_board(req: BoardCreateRequest, token: str = Depends(verify_token)):
    """Create a new, empty board."""
    try:
        db = get_db()
        board_id = str(uuid.uuid4())
        saved = db.create_board(board_id, req.name, req.icon)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=500, detail="Failed to create board")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/boards/{board_id}")
async def get_board(board_id: str, token: str = Depends(verify_token)):
    """Return a single board (with its subcollections attached) by id."""
    try:
        db = get_db()
        board = db.get_board(board_id)
        if board:
            return {"success": True, "data": board}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/boards/{board_id}")
async def rename_board(board_id: str, req: BoardUpdateRequest, token: str = Depends(verify_token)):
    """Rename a board and/or change its icon."""
    try:
        db = get_db()
        saved = db.rename_board(board_id, req.name, req.icon)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/boards/{board_id}")
async def delete_board(board_id: str, token: str = Depends(verify_token)):
    """Delete a board and every subcollection nested under it."""
    try:
        db = get_db()
        ok = db.delete_board(board_id)
        if ok:
            return {"success": True, "message": "Board deleted"}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/boards/{board_id}/posts/{shortcode}")
async def add_post_to_board(board_id: str, shortcode: str, token: str = Depends(verify_token)):
    """Add one post directly to a board (no-op if already present)."""
    try:
        db = get_db()
        saved = db.add_post_to_board(board_id, shortcode)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/boards/{board_id}/posts/{shortcode}")
async def remove_post_from_board(board_id: str, shortcode: str, token: str = Depends(verify_token)):
    """Remove one post from a board's direct post_ids."""
    try:
        db = get_db()
        saved = db.remove_post_from_board(board_id, shortcode)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/boards/{board_id}/subcollections")
async def create_board_subcollection(board_id: str, req: SubcollectionCreateRequest,
                                      token: str = Depends(verify_token)):
    """Create a new, empty subcollection nested under a board."""
    try:
        db = get_db()
        sub_id = str(uuid.uuid4())
        saved = db.create_board_subcollection(sub_id, board_id, req.name, req.icon)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Board not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/boards/{board_id}/subcollections/{sub_id}")
async def rename_board_subcollection(board_id: str, sub_id: str, req: BoardUpdateRequest,
                                      token: str = Depends(verify_token)):
    """Rename a subcollection and/or change its icon."""
    try:
        db = get_db()
        saved = db.rename_board_subcollection(sub_id, req.name, req.icon)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Subcollection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/boards/{board_id}/subcollections/{sub_id}")
async def delete_board_subcollection(board_id: str, sub_id: str, token: str = Depends(verify_token)):
    """Delete a single subcollection (its parent board and siblings are untouched)."""
    try:
        db = get_db()
        ok = db.delete_board_subcollection(sub_id)
        if ok:
            return {"success": True, "message": "Subcollection deleted"}
        raise HTTPException(status_code=404, detail="Subcollection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/boards/{board_id}/subcollections/{sub_id}/posts/{shortcode}")
async def add_post_to_subcollection(board_id: str, sub_id: str, shortcode: str,
                                     token: str = Depends(verify_token)):
    """Add one post to a subcollection (no-op if already present)."""
    try:
        db = get_db()
        saved = db.add_post_to_subcollection(sub_id, shortcode)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Subcollection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/boards/{board_id}/subcollections/{sub_id}/posts/{shortcode}")
async def remove_post_from_subcollection(board_id: str, sub_id: str, shortcode: str,
                                          token: str = Depends(verify_token)):
    """Remove one post from a subcollection."""
    try:
        db = get_db()
        saved = db.remove_post_from_subcollection(sub_id, shortcode)
        if saved:
            return {"success": True, "data": saved}
        raise HTTPException(status_code=404, detail="Subcollection not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check(token: str = Depends(verify_token)):
    """API health check with database connectivity test (requires auth)"""
    try:
        db = get_db()
        stats = db.get_stats()
        
        return {
            "status": "healthy",
            "database": "connected",
            "documents": stats.get('document_count', 0),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.get("/queue-status")
async def queue_status(token: str = Depends(verify_token)):
    """Get current queue and processing status"""
    try:
        db = get_db()
        processing = db.get_processing()
        queue = db.get_queue()

        retry_queue = db.get_retry_queue()
        batch_jobs = db.get_batch_jobs()
        rescan_batch_jobs = db.get_rescan_batch_jobs()
        return {
            "currently_processing": processing,
            "processing_count": len(processing),
            "queue": queue,
            "queue_count": len(queue),
            "retry_queue": retry_queue,
            "retry_count": len(retry_queue),
            "batch_pending": batch_jobs,
            "batch_count": len(batch_jobs),
            # In-flight rescan-pipeline batch jobs (core/rescan_batch_processor.py)
            # — a separate surface from batch_pending above, since a rescan
            # target is never in processing_queue once it reaches this state
            # (see enqueue_rescan_batch_job's comment in core/database.py).
            "rescan_batch_pending": rescan_batch_jobs,
            "rescan_batch_count": len(rescan_batch_jobs),
            "analysis_mode": ANALYSIS_MODE,
            "max_concurrent": max_concurrent,
            "available_slots": max(0, max_concurrent - len(processing))
        }
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/batches/check")
async def check_batches(token: str = Depends(verify_token)):
    """
    Manually trigger a check of in-flight OpenAI Batch API jobs
    (ANALYSIS_MODE=batch): advances completed summary batches to importance+
    embedding batches, and finalizes items whose scoring batches are done
    into the `analyses` table. This is the only way (besides the automatic
    startup check) that batch-pending items make progress — there is no
    periodic polling. Called by the "Check batches" button in superbrain-web.
    """
    try:
        from core.batch_processor import check_and_advance_batches
        result = await asyncio.to_thread(check_and_advance_batches)
        return {"success": True, "analysis_mode": ANALYSIS_MODE, **result}
    except Exception as e:
        logger.error(f"Batch check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rescan/batches/check")
async def check_rescan_batches(token: str = Depends(verify_token)):
    """
    Same idea as POST /batches/check, but for the separate rescan pipeline's
    OpenAI Batch API jobs (core/rescan_batch_processor.py) — see "Rescan
    pipeline" in backend/CLAUDE.md. Distinct route/function/table from
    POST /batches/check on purpose; the two pipelines don't share state.
    """
    try:
        from core.rescan_batch_processor import check_and_advance_rescan_batches
        result = await asyncio.to_thread(check_and_advance_rescan_batches)
        return {"success": True, "analysis_mode": ANALYSIS_MODE, **result}
    except Exception as e:
        logger.error(f"Rescan batch check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/eloquence/batches/check")
async def check_eloquence_batches(token: str = Depends(verify_token)):
    """
    Same idea as POST /batches/check, but for scripts/score_eloquence.py
    --batch's OpenAI Batch API jobs (core/eloquence_batch_processor.py).
    Distinct route/function/table from the other two batch-check endpoints —
    the eloquence backfill doesn't share state with first-analysis or rescan.
    """
    try:
        from core.eloquence_batch_processor import check_and_advance_eloquence_batches
        result = await asyncio.to_thread(check_and_advance_eloquence_batches)
        return {"success": True, "analysis_mode": ANALYSIS_MODE, **result}
    except Exception as e:
        logger.error(f"Eloquence batch check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/eloquence/override")
async def override_eloquence(payload: dict, token: str = Depends(verify_token)):
    """
    Manual human correction for one or more posts the AI eloquence judge
    (core/eloquence.py) got wrong — flips is_eloquent to False so a false
    positive from scripts/score_eloquence.py drops out of the /eloquent
    page. db.override_eloquence_not_eloquent() logs each post's prior
    AI verdict/rationale to eloquence_overrides before overwriting it, so
    GET /eloquence/overrides can later be reviewed to refine
    ELOQUENCE_PROMPT — that's also why a shortcode that was already not
    eloquent is bucketed separately rather than counted as 'updated': it's
    not a fresh correction worth logging again.
    """
    shortcodes = payload.get("shortcodes")
    if not isinstance(shortcodes, list) or not shortcodes or not all(isinstance(s, str) for s in shortcodes):
        raise HTTPException(status_code=400, detail="shortcodes must be a non-empty list of strings")

    db = get_db()
    updated, already_not_eloquent, not_found = [], [], []
    for shortcode in shortcodes:
        result = db.override_eloquence_not_eloquent(shortcode)
        if result == "overridden":
            updated.append(shortcode)
        elif result == "already_not_eloquent":
            already_not_eloquent.append(shortcode)
        else:
            not_found.append(shortcode)

    logger.info(f"✅ Manually marked not eloquent: {updated}")
    return {
        "success": True,
        "updated": updated,
        "already_not_eloquent": already_not_eloquent,
        "not_found": not_found,
    }


@app.post("/eloquence/approve")
async def approve_eloquence(payload: dict, token: str = Depends(verify_token)):
    """
    The other half of the /eloquent page's per-card review: a human looked
    at the post and agrees it belongs there. Stamps analyses.eloquence_reviewed
    = 1 (db.approve_eloquence()) so the page can hide its approve/reject
    buttons for that card and filter to "unreviewed" — otherwise every fresh
    scoring run's new arrivals are indistinguishable from posts already
    checked. Nothing else changes; the verdict itself was already eloquent.
    """
    shortcodes = payload.get("shortcodes")
    if not isinstance(shortcodes, list) or not shortcodes or not all(isinstance(s, str) for s in shortcodes):
        raise HTTPException(status_code=400, detail="shortcodes must be a non-empty list of strings")

    db = get_db()
    buckets = {"approved": [], "already_approved": [], "not_eloquent": [], "not_found": []}
    for shortcode in shortcodes:
        buckets[db.approve_eloquence(shortcode)].append(shortcode)

    logger.info(f"✅ Eloquence approved: {buckets['approved']}")
    return {"success": True, **buckets}


@app.get("/eloquence/overrides")
async def list_eloquence_overrides(token: str = Depends(verify_token)):
    """Audit log of manual eloquence corrections (POST /eloquence/override) —
    each entry keeps the AI's original verdict/rationale so a cluster of
    similar overrides can point at what to fix in ELOQUENCE_PROMPT
    (core/eloquence.py)."""
    db = get_db()
    return {"success": True, "overrides": db.get_eloquence_overrides()}


# ── Eloquence scoring from the admin panel ───────────────────────────────
# Web-driven equivalent of scripts/score_eloquence.py: the candidate count
# is previewed first (GET /eloquence/candidates) so the user can decide how
# many to spend LLM calls on (POST /eloquence/score {limit}), instead of
# the script's all-or-nothing run. Both share the script's own helpers so
# the CLI and the panel can't disagree on what "passes the criteria".
#
# Job state is in-memory only (no table): each post's verdict is written to
# `analyses` the moment it's scored, so a backend restart mid-run loses
# nothing but the progress readout — the unscored remainder simply shows up
# as candidates again. Single job at a time (409 otherwise), same as the
# import jobs.

_ELOQUENCE_SCORE_LOG_MAX_LINES = 200
_eloquence_score_job: Optional[dict] = None
_eloquence_score_lock = threading.Lock()


class EloquenceScoreRequest(BaseModel):
    # None = every candidate ("Score all"); otherwise only the first N.
    limit: Optional[int] = None
    # Re-score posts that already have a verdict (scripts/score_eloquence.py
    # --force) — e.g. after an ELOQUENCE_PROMPT change.
    force: bool = False


def _eloquence_job_snapshot() -> Optional[dict]:
    with _eloquence_score_lock:
        if _eloquence_score_job is None:
            return None
        job = dict(_eloquence_score_job)
        job["log_tail"] = "".join(job.pop("_log_lines"))
        return job


def _run_eloquence_score_job(job_id: str, candidates: list, analysis_mode: str):
    """Background thread body for POST /eloquence/score. Drives
    scripts/score_eloquence.py's run_immediate()/run_batch() directly (the
    sys.path insert for the scripts dir happens further down this file, at
    import time, so a lazy import here resolves)."""
    import score_eloquence as _score  # noqa: E402  (scripts/ is on sys.path)

    db = get_db()

    def _log(line: str):
        with _eloquence_score_lock:
            lines = _eloquence_score_job["_log_lines"]
            lines.append(line if line.endswith("\n") else line + "\n")
            del lines[:-_ELOQUENCE_SCORE_LOG_MAX_LINES]

    def _on_result(index: int, row: dict, verdict):
        with _eloquence_score_lock:
            job = _eloquence_score_job
            job["processed"] = index
            if verdict is None:
                job["failed"] += 1
            elif verdict:
                job["eloquent"] += 1
            else:
                job["not_eloquent"] += 1
        label = "FAILED (no parseable verdict)" if verdict is None else ("ELOQUENT" if verdict else "not eloquent")
        _log(f"[{index}/{len(candidates)}] {row['shortcode']} — {row['title']!r}: {label}")

    try:
        if analysis_mode == "batch":
            result = _score.run_batch(db, candidates)
            with _eloquence_score_lock:
                _eloquence_score_job.update(
                    processed=result["submitted"], submitted=result["submitted"],
                    batch_jobs=result["batch_jobs"],
                )
            _log(
                f"Submitted {result['submitted']} post(s) across {result['batch_jobs']} batch job(s). "
                "Results land on the next backend startup or POST /eloquence/batches/check."
            )
        else:
            _score.run_immediate(db, candidates, on_result=_on_result)
        with _eloquence_score_lock:
            _eloquence_score_job.update(status="complete", finished_at=datetime.utcnow().isoformat())
    except Exception as e:
        logger.error(f"Eloquence scoring job {job_id} failed: {e}")
        with _eloquence_score_lock:
            _eloquence_score_job.update(
                status="failed", finished_at=datetime.utcnow().isoformat(), error=str(e),
            )


@app.get("/eloquence/candidates")
async def eloquence_candidates(force: bool = False, token: str = Depends(verify_token)):
    """
    How many posts would scripts/score_eloquence.py score right now, with
    the same selection it uses (length threshold → not-yet-scored unless
    force → no batch in flight → filler-ratio pre-filter). The breakdown
    counts are returned so the admin panel can explain a small number.
    Nothing is scored here — this is the preview before POST /eloquence/score.
    """
    from core.eloquence import LENGTH_THRESHOLD, select_eloquence_candidates

    db = get_db()
    sel = await asyncio.to_thread(select_eloquence_candidates, db, force)
    return {
        "success": True,
        "analysis_mode": ANALYSIS_MODE,
        "length_threshold": LENGTH_THRESHOLD,
        "force": force,
        "candidate_count": len(sel["candidates"]),
        "total_over_threshold": sel["total_over_threshold"],
        "skipped_pending": sel["skipped_pending"],
        "skipped_prefilter": sel["skipped_prefilter"],
    }


@app.post("/eloquence/score")
async def start_eloquence_score(req: EloquenceScoreRequest, token: str = Depends(verify_token)):
    """
    Score the first `limit` current candidates (all of them when limit is
    null) in a background thread and return immediately with the job; poll
    GET /eloquence/score/status. Honors ANALYSIS_MODE exactly like the
    script: `immediate` scores synchronously post by post (the job stays
    'running' until the last one), `batch` submits OpenAI Batch jobs and
    completes as soon as they're submitted.

    Candidates are re-selected at start time, so the count the panel
    previewed may differ slightly if posts were analyzed in between.
    """
    global _eloquence_score_job

    if req.limit is not None and req.limit < 1:
        raise HTTPException(status_code=400, detail="limit must be a positive integer or null.")

    from core.eloquence import select_eloquence_candidates

    with _eloquence_score_lock:
        if _eloquence_score_job and _eloquence_score_job["status"] == "running":
            raise HTTPException(status_code=409, detail="An eloquence scoring job is already running.")

    db = get_db()
    sel = await asyncio.to_thread(select_eloquence_candidates, db, req.force)
    candidates = sel["candidates"]
    if not candidates:
        raise HTTPException(status_code=400, detail="No posts currently pass the eloquence criteria.")
    if req.limit is not None:
        candidates = candidates[:req.limit]

    job_id = uuid.uuid4().hex
    with _eloquence_score_lock:
        # Re-check under the lock — two clicks racing past the check above
        # must not both start a thread.
        if _eloquence_score_job and _eloquence_score_job["status"] == "running":
            raise HTTPException(status_code=409, detail="An eloquence scoring job is already running.")
        _eloquence_score_job = {
            "id": job_id,
            "status": "running",
            "analysis_mode": ANALYSIS_MODE,
            "force": req.force,
            "requested": req.limit,
            "total": len(candidates),
            "candidate_count": len(sel["candidates"]),
            "processed": 0,
            "eloquent": 0,
            "not_eloquent": 0,
            "failed": 0,
            "submitted": 0,
            "batch_jobs": 0,
            "error": None,
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "_log_lines": [
                f"Scoring {len(candidates)} of {len(sel['candidates'])} candidate(s) "
                f"(mode: {ANALYSIS_MODE}{', re-scoring already-scored' if req.force else ''}).\n"
            ],
        }

    threading.Thread(
        target=_run_eloquence_score_job, args=(job_id, candidates, ANALYSIS_MODE), daemon=True,
    ).start()
    logger.info(f"🎙️ Eloquence scoring job {job_id}: {len(candidates)} post(s), mode={ANALYSIS_MODE}")
    return {"success": True, "data": _eloquence_job_snapshot()}


@app.get("/eloquence/score/status")
async def eloquence_score_status(token: str = Depends(verify_token)):
    """The most recent POST /eloquence/score job (running or finished) since
    this backend process started, or null — in-memory only, see the comment
    above _eloquence_score_job."""
    return {"success": True, "data": _eloquence_job_snapshot()}


@app.delete("/post/{shortcode}")
async def delete_post(shortcode: str, token: str = Depends(verify_token)):
    """Delete a post by shortcode, killing any active analysis subprocess"""
    try:
        db = get_db()

        # Kill active analysis subprocess if this post is currently being processed
        with _active_processes_lock:
            proc = _active_processes.pop(shortcode, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info(f"🛑 Killed active analysis for: {shortcode}")

        # Remove from queue (handles both 'queued' and 'processing' states)
        db.remove_from_queue(shortcode)

        result = db.delete_post(shortcode)

        if result:
            logger.info(f"✅ Deleted post: {shortcode}")
            return {
                "success": True,
                "message": "Post deleted successfully",
                "shortcode": shortcode
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting post: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/post/{shortcode}")
async def update_post(shortcode: str, updates: dict, token: str = Depends(verify_token)):
    """Update a post's category, title, summary, or mark it as reviewed"""
    try:
        db = get_db()

        # Only allow specific fields to be updated.
        # 'reviewed': true clears the needs_review flag (see db.update_post)
        # without re-running analysis — used when a post from before a
        # pipeline change turns out to already be good enough.
        allowed_fields = {
            'category', 'language', 'title', 'summary', 'reviewed',
            'enjoyment_rating', 'perceived_importance_rating', 'should_revisit',
        }
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        for field in ('enjoyment_rating', 'perceived_importance_rating'):
            if field in filtered_updates and filtered_updates[field] not in RATING_VALUES:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field} must be null, 'liked', or 'loved'"
                )

        if 'should_revisit' in filtered_updates and not isinstance(filtered_updates['should_revisit'], bool):
            raise HTTPException(status_code=400, detail="should_revisit must be a boolean")

        result = db.update_post(shortcode, filtered_updates)
        
        if result:
            logger.info(f"✅ Updated post: {shortcode} - {list(filtered_updates.keys())}")
            return {
                "success": True,
                "message": "Post updated successfully",
                "shortcode": shortcode,
                "updated_fields": list(filtered_updates.keys())
            }
        else:
            raise HTTPException(status_code=404, detail="Post not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating post: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------
# Personalization signals — feed superbrain-web's Home recommendation
# engine (src/lib/recommendations.ts). Deliberately NOT folded into
# /export: that payload is cached wholesale by every client, and a view
# log firing on every post open would invalidate/blow away the expensive
# posts+clustering cache for no reason. These are read separately instead.
# ----------------------------------------------------------------------

@app.post("/post/{shortcode}/view")
async def log_post_view(
    shortcode: str,
    token: str = Depends(verify_token),
    x_client_env: Optional[str] = Header(default=None, description="'dev' from a local `next dev` session; omitted/anything else counts as real usage")
):
    """Log a qualifying view (video >=60% watched, or non-video open >=20s —
    see superbrain-web's useQualifyingView hook for what qualifies). The
    frontend fires this fire-and-forget, so failures here should never
    surface to the user — return success:false rather than raising where
    reasonable."""
    try:
        db = get_db()
        ok = db.log_post_view(shortcode, client_env=resolve_client_env(x_client_env))
        return {"success": ok, "shortcode": shortcode}
    except Exception as e:
        logger.error(f"Error logging post view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/view-history")
async def get_view_history(
    since: Optional[str] = Query(default=None, description="ISO timestamp; only return views at or after this time"),
    limit: int = Query(default=5000, ge=1, le=20000),
    token: str = Depends(verify_token)
):
    try:
        db = get_db()
        results = db.get_view_history(since=since, limit=limit)
        return {"success": True, "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"Error fetching view history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-guide-reel-history")
async def get_study_guide_reel_history(
    since: Optional[str] = Query(default=None, description="ISO timestamp; only return links created at or after this time"),
    limit: int = Query(default=20000, ge=1, le=20000),
    token: str = Depends(verify_token)
):
    """Read-side of the reels_study_guide signal (see that table's CREATE
    comment in core/database.py) — the Home recommendation engine's weaker,
    separate-from-post_views "used as study guide source material" history.
    Each row's opened_at reflects its owning collection's last_opened_at."""
    try:
        db = get_db()
        results = db.get_study_guide_reel_history(since=since, limit=limit)
        return {"success": True, "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"Error fetching study guide reel history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search-history")
async def get_search_history(
    since: Optional[str] = Query(default=None, description="ISO timestamp; only return queries at or after this time"),
    limit: int = Query(default=2000, ge=1, le=10000),
    token: str = Depends(verify_token)
):
    try:
        db = get_db()
        results = db.get_search_history(since=since, limit=limit)
        return {"success": True, "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"Error fetching search history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/retry")
async def get_retry_queue(token: str = Depends(verify_token)):
    """Show all items currently scheduled for automatic retry"""
    try:
        items = db.get_retry_queue()
        return {
            "retry_queue": items,
            "count": len(items)
        }
    except Exception as e:
        logger.error(f"Error fetching retry queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/retry/flush")
async def flush_retry_queue(
    force: bool = Query(
        False,
        description="Also promote items whose retry_after is still in the future, "
                    "ignoring the scheduled wait entirely.",
    ),
    token: str = Depends(verify_token),
):
    """
    Promote retry-queued items back into the active queue right now.

    By default this only takes items whose `retry_after` has already passed —
    the same set queue_worker()'s periodic drain would pick up on its own, so
    calling it just makes that happen sooner.

    `force=true` ignores `retry_after` and promotes every status='retry' row.
    That's the "don't wait 24 hours" button. Worth knowing before using it:
    nearly all of these are waiting because Instagram rate-limited the
    download, and that block is time-based — flushing them early mostly
    re-attempts requests that will fail again and be re-queued, and hammering
    a live block can extend it. It costs nothing but time (a failed download
    never reaches the AI providers), and max_concurrent is 1, so a large
    flush drains one reel at a time rather than in a burst.
    """
    try:
        db = get_db()
        items = db.get_retry_queue() if force else db.get_retry_ready()
        for item in items:
            db.add_to_queue(item['shortcode'], item['url'])
            logger.info(f"🔄 Flushed retry item: {item['shortcode']} ({item['reason']})")
        if force:
            logger.warning(f"⏩ Force-flushed {len(items)} retry item(s), ignoring their scheduled wait")
        return {
            "flushed": len(items),
            "forced": force,
            "items": [i['shortcode'] for i in items]
        }
    except Exception as e:
        logger.error(f"Error flushing retry queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/queue/{shortcode}")
async def delete_queue_item(shortcode: str, token: str = Depends(verify_token)):
    """Remove an item from the processing or retry queue"""
    try:
        db = get_db()
        db.remove_from_queue(shortcode)
        return {"success": True, "message": f"Removed {shortcode} from queue"}
    except Exception as e:
        logger.error(f"Error removing {shortcode} from queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────
# Stuck-reel triage + manual media upload
#
# A reel can stop making progress in two different places, and neither one
# is visible from /queue-status alone:
#
#   1. processing_queue — queued / processing / retry / batch. Still being
#      worked on (a status='retry' row is retried automatically after
#      retry_after), so: pending.
#   2. scripts/import_state.json — the bulk importer's resumable state. A
#      hard analysis failure is *deleted* from processing_queue by
#      _run_or_queue_analysis's cleanup, so the DB keeps no record of it at
#      all; the only trace is this file's per-URL entry. Its
#      "permanently_skipped" status (max_attempts exhausted, or an HTTP 410)
#      is the one that means nothing will ever retry this again.
#
# GET /queue/attention reconciles both against the `analyses` table so
# "still stuck" is distinguishable from "the state file just hasn't caught
# up yet", and POST /manual-upload is the way out for the abandoned ones:
# hand over the video yourself and analyze that instead of re-attempting a
# download Instagram keeps refusing.
#
# Deliberately read-only with respect to import_state.json — a bulk import
# job may be running and writing that file right now, and the backend
# racing it over the same non-atomic state would lose entries. A manual
# upload lands in `analyses` instead, and the importer's next run sees a
# cache hit and marks it success on its own.
# ─────────────────────────────────────────────────────────────────

def _import_state_file() -> Path:
    """Path of the bulk importer's resumable state file.

    Read from the import script itself rather than rebuilt here, so this and
    the scripts can never disagree about which file is authoritative. A
    function, not a module constant, because `_ig_import` is imported much
    further down this file (next to the /instagram-export routes it mainly
    serves) — resolving it at call time avoids a load-order dependency.
    """
    return Path(_ig_import.DEFAULT_STATE_FILE)


def _read_import_state() -> dict:
    """Read the bulk importer's resumable state file, tolerating absence.

    save_state() writes via os.replace(), so a read is always of a complete
    file even while an import job is running — but the file may legitimately
    not exist yet (no import has ever been run), which is not an error.
    """
    try:
        state_file = _import_state_file()
        if not state_file.exists():
            return {}
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read import state file: {e}")
        return {}


def _instagram_url_for(shortcode: str) -> str:
    """Best-effort canonical reel URL for a shortcode with no recorded URL."""
    return f"https://www.instagram.com/reel/{shortcode}/"


@app.get("/queue/attention")
async def queue_attention(
    include_analyzed: bool = Query(
        False,
        description="Include items whose shortcode already has a row in `analyses` "
                    "(the state file lags reality until the importer next runs).",
    ),
    include_deleted: bool = Query(
        False, description="Include items the user has since deleted."
    ),
    token: str = Depends(verify_token),
):
    """
    Every reel that is either still pending or abandoned, in one list.

    Returns two buckets:
      - `pending`   — will still be attempted (live queue row, or a state
                      file entry the importer hasn't reached yet).
      - `abandoned` — nothing will retry this: the importer gave up on it
                      (max attempts, or the post is gone). These are the
                      ones POST /manual-upload exists for.
    """
    try:
        db = get_db()
        analyzed = db.get_analyzed_shortcodes()
        deleted = db.get_deleted_shortcodes()

        items: Dict[str, dict] = {}

        # ── 1. Live queue rows ───────────────────────────────────────────
        for row in db.get_queue_overview():
            shortcode = row.get("shortcode")
            if not shortcode:
                continue
            items[shortcode] = {
                "shortcode": shortcode,
                "url": row.get("url") or _instagram_url_for(shortcode),
                "bucket": "pending",
                "state": row.get("status") or "queued",
                "source": "queue",
                "content_type": row.get("content_type") or "instagram",
                "reason": row.get("reason"),
                "last_error": None,
                "attempts": row.get("attempts") or 0,
                "retry_after": row.get("retry_after"),
                "position": row.get("position"),
                "folders": [],
                "last_updated": row.get("updated_at") or row.get("added_at"),
            }

        # ── 2. Importer state file ───────────────────────────────────────
        for url, entry in (_read_import_state().get("posts") or {}).items():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if status == "success":
                continue
            shortcode = entry.get("shortcode") or _ig_import.shortcode_for(url)
            if not shortcode:
                continue

            existing = items.get(shortcode)
            if existing:
                # A live queue row is the more current truth about *state*;
                # the state file still carries context the queue never had
                # (which Instagram folders it came from, the last error text
                # the importer actually saw).
                existing["folders"] = entry.get("folders") or []
                existing["last_error"] = entry.get("last_error")
                existing["attempts"] = max(
                    existing["attempts"], entry.get("attempts") or 0
                )
                continue

            abandoned = status == "permanently_skipped"
            items[shortcode] = {
                "shortcode": shortcode,
                "url": url,
                "bucket": "abandoned" if abandoned else "pending",
                "state": "abandoned" if abandoned else "import_pending",
                "source": "import_state",
                "content_type": "instagram",
                "reason": None,
                "last_error": entry.get("last_error"),
                "attempts": entry.get("attempts") or 0,
                "retry_after": None,
                "position": None,
                "folders": entry.get("folders") or [],
                "last_updated": entry.get("last_updated"),
            }

        # ── 3. Reconcile against reality ─────────────────────────────────
        pending, abandoned_items = [], []
        hidden_analyzed = hidden_deleted = 0
        for item in items.values():
            item["analyzed"] = item["shortcode"] in analyzed
            item["deleted"] = item["shortcode"] in deleted
            if item["deleted"] and not include_deleted:
                hidden_deleted += 1
                continue
            if item["analyzed"] and not include_analyzed:
                hidden_analyzed += 1
                continue
            (abandoned_items if item["bucket"] == "abandoned" else pending).append(item)

        def _sort_key(i: dict):
            return (i.get("last_updated") or "", i["shortcode"])

        pending.sort(key=_sort_key, reverse=True)
        abandoned_items.sort(key=_sort_key, reverse=True)

        return {
            "success": True,
            "pending": pending,
            "pending_count": len(pending),
            "abandoned": abandoned_items,
            "abandoned_count": len(abandoned_items),
            "hidden_analyzed": hidden_analyzed,
            "hidden_deleted": hidden_deleted,
            "state_file": str(_import_state_file()),
            "state_file_present": _import_state_file().exists(),
        }
    except Exception as e:
        logger.error(f"Error building attention queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/manual-upload")
async def manual_upload(
    url: str = Form(..., description="The original Instagram post/reel URL."),
    file: UploadFile = File(..., description="The video or image, obtained by hand."),
    caption: str = Form("", description="Optional caption text to analyze alongside the media."),
    username: str = Form("", description="Optional author handle, stored on the post."),
    token: str = Depends(verify_token),
):
    """
    Analyze a reel from a manually supplied file instead of downloading it.

    For posts Instagram will not serve this backend (rate limited, login
    walled, or removed) but that the user can still get some other way. The
    upload is normalized into a folder shaped exactly like a download
    (core/manual_media.py) and handed to the normal pipeline via `main.py
    --media-folder`, so the resulting post is indistinguishable from any
    other — same analyzers, same media/<shortcode>/ storage, same row.
    """
    validation = validate_link(url)
    if not validation.get("valid"):
        raise HTTPException(
            status_code=400,
            detail=validation.get("error") or "That doesn't look like a valid link.",
        )
    if validation.get("content_type") != "instagram":
        raise HTTPException(
            status_code=400,
            detail="Manual upload is for Instagram posts only — YouTube and web "
                   "pages are analyzed from their URL and never need a media file.",
        )

    shortcode = validation["shortcode"]
    url_str = validation["url"]

    try:
        data = await file.read()
    finally:
        await file.close()

    from core.manual_media import ManualMediaError, prepare_manual_media_folder

    try:
        folder = await asyncio.to_thread(
            prepare_manual_media_folder,
            shortcode, url_str, file.filename or "", data, caption, username,
        )
    except ManualMediaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ [{shortcode}] Could not prepare manual media: {e}")
        raise HTTPException(status_code=500, detail=f"Could not prepare the uploaded file: {e}")

    logger.info(f"📤 [{shortcode}] Manual media upload — analyzing from {folder}")

    # Re-analyze even if a row already exists: someone uploading media by
    # hand is explicitly replacing whatever is there (typically nothing, or
    # a stub from a failed run). save_analysis() upserts.
    # "queued" is the one outcome where the uploaded file is still needed —
    # it stays on disk with processing_queue.media_folder pointing at this
    # exact path, so queue_worker can use it instead of re-downloading.
    # Every other outcome means main.py is done with the folder: it either
    # relocated the media into media/<shortcode>/ (success, and both 202
    # paths — batch-submitted and retry-scheduled — relocate before exiting),
    # or it short-circuited on its own cache check and never touched it
    # (uploading a post that turns out to be already analyzed), which would
    # otherwise orphan a full copy of the video in temp/ forever.
    try:
        result = await _run_or_queue_analysis(
            shortcode, url_str, "instagram",
            caption=caption or None,
            media_folder=str(folder),
        )
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    if result.get("status") != "queued":
        shutil.rmtree(folder, ignore_errors=True)

    return {"success": True, "shortcode": shortcode, **result}


# ─────────────────────────────────────────────────────────────────
# Reset endpoints (admin only)
# ─────────────────────────────────────────────────────────────────

@app.post("/reset/api-token")
async def reset_api_token(token: str = Depends(verify_token)):
    """
    Reset the API token. A new token will be generated.
    - Requires API authentication
    - Returns the new token
    """
    global API_TOKEN
    try:
        # Generate new 8-character alphanumeric token
        new_token = generate_api_token()
        
        # Save to file
        TOKEN_FILE.write_text(new_token)
        
        # Update in-memory token so it takes effect immediately
        API_TOKEN = new_token
        
        logger.warning("API token was reset by a client")
        
        return {
            "success": True,
            "new_token": new_token,
            "message": "API token has been reset. Update this token in your mobile app settings."
        }
    except Exception as e:
        logger.error(f"Error resetting API token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset/database")
async def reset_database(
    token: str = Depends(verify_token),
    confirm: str = Body(..., description="Must be 'DELETE_ALL' to confirm")
):
    """
    Reset (clear) the database. This will delete all posts and collections.
    - Requires API authentication
    - Requires confirm='DELETE_ALL' in body
    """
    if confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail="Confirmation required: pass confirm='DELETE_ALL'")
    
    try:
        db = get_db()

        # Delete all posts/collections/queue entries in SQLite
        conn = db._conn
        cur_posts = conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM collections")
        conn.execute("DELETE FROM processing_queue")

        # Recreate the permanently-seeded collections (Watch Later, iPhone)
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ('default_watch_later', 'Watch Later', 'time', '[]', now, now)
        )
        conn.execute(
            "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ('iphone_shares', 'iPhone', '📱', '[]', now, now)
        )
        conn.commit()

        deleted_count = cur_posts.rowcount
        
        logger.warning(f"🗑️ Database was reset by a client. Deleted {deleted_count} posts.")
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Database cleared. {deleted_count} posts deleted."
        }
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────
# Import/Export endpoints
# ─────────────────────────────────────────────────────────────────

# Last GET /embeddings response, keyed by get_embeddings_fingerprint() so
# repeat requests skip re-parsing every stored vector's JSON text.
_embeddings_blob_cache: Dict[str, Any] = {"fingerprint": None, "blob": None}


def _build_embeddings_blob(db) -> tuple:
    """Pack every non-hidden post's embedding as little-endian float32.

    Layout: uint32 LE header length | UTF-8 JSON header, space-padded so the
    vectors start 4-byte aligned | float32 LE vectors, count x dim, in the
    header's shortcode order. Header: {"fingerprint", "dim", "count",
    "shortcodes"}. Vectors whose length isn't the library's most common
    dimension are skipped rather than mis-framing everything after them.
    """
    from array import array
    from collections import Counter
    import struct

    fingerprint = db.get_embeddings_fingerprint()
    if fingerprint and _embeddings_blob_cache["fingerprint"] == fingerprint:
        return fingerprint, _embeddings_blob_cache["blob"]

    rows = db.get_all_embeddings()
    dims = Counter(len(r["embedding"]) for r in rows)
    dim = dims.most_common(1)[0][0] if dims else 0
    shortcodes = []
    values = array("f")
    for r in rows:
        if len(r["embedding"]) != dim:
            continue
        shortcodes.append(r["shortcode"])
        values.extend(r["embedding"])
    if sys.byteorder != "little":
        values.byteswap()

    header = json.dumps(
        {"fingerprint": fingerprint, "dim": dim, "count": len(shortcodes), "shortcodes": shortcodes}
    ).encode("utf-8")
    header += b" " * ((-(4 + len(header))) % 4)
    blob = struct.pack("<I", len(header)) + header + values.tobytes()

    _embeddings_blob_cache["fingerprint"] = fingerprint
    _embeddings_blob_cache["blob"] = blob
    return fingerprint, blob


@app.get("/embeddings")
async def get_embeddings(token: str = Depends(verify_token)):
    """
    Every non-hidden post's embedding as one binary float32 blob (see
    _build_embeddings_blob for the layout) — about 6 KB per post versus
    ~30 KB of JSON text in /export, and readable client-side as a
    Float32Array with no parsing. Pair with /export?include_embeddings=false:
    its `embeddings_fingerprint` matches the X-Embeddings-Fingerprint header
    here, so clients only refetch when the vectors actually changed.

    Requires API authentication.
    """
    try:
        fingerprint, blob = _build_embeddings_blob(get_db())
        return Response(
            content=blob,
            media_type="application/octet-stream",
            headers={"X-Embeddings-Fingerprint": fingerprint},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export")
async def export_data(
    background_tasks: __import__('fastapi').BackgroundTasks,
    token: str = Depends(verify_token),
    limit: int = Query(default=10000, ge=1, le=50000, description="Max posts to export"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    format: str = Query(default="json", description="Export format: json or zip"),
    include_embeddings: bool = Query(default=True, description="Include each post's embedding vector"),
):
    """
    Export data as JSON or ZIP (posts, collections, settings).
    - Requires API authentication
    - Supports pagination with limit and offset
    - include_embeddings=false drops each post's `embedding` (~30 KB of JSON
      text per post, 90%+ of the payload) and adds a top-level
      `embeddings_fingerprint` instead; fetch the vectors from GET /embeddings.
      superbrain-web does this — a full-library export with embeddings grew
      past V8's max string length. Defaults to true so backups stay complete
      for /import.
    """
    import tempfile
    import os
    import httpx
    
    try:
        db = get_db()
        
        # Get posts with pagination using SQLite
        posts = db.get_all_posts(limit=limit, offset=offset)
        # Convert sqlite3.Row objects to fully mutable dictionaries
        posts_list = [dict(p) for p in posts]
        
        collections = db.get_all_collections()
        stats = db.get_stats()
        
        export_payload = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "posts": posts_list,
            "collections": collections,
            "stats": stats
        }
        if not include_embeddings:
            for p in posts_list:
                p.pop("embedding", None)
            export_payload["embeddings_fingerprint"] = db.get_embeddings_fingerprint()
        
        if format.lower() == "zip":
            # Create a zip file on disk to avoid memory explosion
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            zip_path = tmp.name
            tmp.close()
            
            async def download_image(client, sem, post_dict):
                url = post_dict.get('thumbnail_url') or post_dict.get('thumbnail')
                if not url:
                    return None
                    
                shortcode = post_dict.get('shortcode')
                if not shortcode: return None

                if url.startswith("/static/"):
                    local_path = url.replace("/static/", "", 1)
                    full_path = _STATIC_DIR / local_path
                    try:
                        if full_path.exists():
                            with open(full_path, "rb") as f:
                                return (local_path, f.read())
                    except Exception as e:
                        logger.error(f"Failed bundling local image {url}: {e}")
                    return None

                # Handle base64 encoded data URIs commonly saved by main.py
                if url.startswith("data:image/"):
                    try:
                        import base64
                        header, encoded = url.split(',', 1)
                        ext = "jpg"
                        if "png" in header.lower(): ext = "png"
                        elif "webp" in header.lower(): ext = "webp"
                        
                        img_data = base64.b64decode(encoded)
                        path_in_zip = f"thumbnails/{shortcode}.{ext}"
                        post_dict['thumbnail'] = f"/static/{path_in_zip}"
                        return (path_in_zip, img_data)
                    except Exception as e:
                        logger.error(f"Failed decoding base64 image for {shortcode}: {e}")
                        return None
                        
                ext = "jpg"
                if ".png" in url.lower(): ext = "png"
                elif ".webp" in url.lower(): ext = "webp"
                
                path_in_zip = f"thumbnails/{shortcode}.{ext}"
                try:
                    async with sem:
                        resp = await client.get(url, follow_redirects=True, timeout=12.0)
                        if resp.status_code == 200:
                            post_dict['thumbnail'] = f"/static/{path_in_zip}"
                            return (path_in_zip, resp.content)
                except Exception as e:
                    logger.warning(f"Failed to fetch thumbnail for {shortcode}: {e}")
                return None

            # Fetch all thumbnails concurrently in batches
            sem = asyncio.Semaphore(15)
            tasks = []
            async with httpx.AsyncClient(verify=False) as client:
                for post in export_payload["posts"]:
                    tasks.append(download_image(client, sem, post))
                
                downloaded_images = await asyncio.gather(*tasks)

            # Write everything to the zip sequentially to save RAM
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # The export_payload now has updated 'thumbnail' fields pointing locally
                zip_file.writestr("superbrain_export.json", json.dumps(export_payload, default=str))
                for res in downloaded_images:
                    if res:
                        path_in_zip, content = res
                        zip_file.writestr(path_in_zip, content)
                        
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"superbrain_export_{timestamp}.zip"
            
            background_tasks.add_task(os.remove, zip_path)
            return FileResponse(zip_path, media_type="application/zip", filename=filename)
        
        # Default JSON response
        return export_payload
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────
# Instagram export import (superbrain-web's /import page)
#
# Deliberately a distinct URL prefix from /import & /import/file below —
# those restore a SuperBrain-format /export backup (ImportData/
# _process_import_data), a completely different operation from ingesting a
# fresh Instagram "Download Your Information" export and running it through
# the full analysis pipeline over minutes/hours. Reuses
# scripts/import_saved_instagram.py's parsing/reversal logic directly
# (sibling-module import, same trick import_saved_instagram_by_collection.py
# already uses) rather than re-implementing it here.
# ─────────────────────────────────────────────────────────────────────────

_INSTAGRAM_EXPORT_SCRIPTS_DIR = Path(__file__).parent / "scripts"
_INSTAGRAM_EXPORT_UPLOADS_DIR = Path(__file__).parent / "uploads"
_INSTAGRAM_EXPORT_LOG_MAX_CHARS = 50_000

sys.path.insert(0, str(_INSTAGRAM_EXPORT_SCRIPTS_DIR))
import import_saved_instagram as _ig_import  # noqa: E402


class InstagramExportPreviewRequest(BaseModel):
    # Instagram's "Download Your Information" export root can be a list of
    # collections (the shape confirmed against a real saved_collections.json
    # — see extract_meta_label_values_shape()) or, for some other export
    # variants, a dict — see _known_shape_items()'s Shape A/B. Never assume dict.
    export_data: Any
    # Optional flat "every saved post, ungrouped" export (saved_posts.json-
    # shaped) — when given, the preview also reports how many of
    # export_data's posts already have a known real save date in it. Never
    # a source of URLs itself — see extract_post_timestamps().
    all_posts_data: Any = None


class InstagramExportJobCreate(BaseModel):
    export_data: Any
    all_posts_data: Any = None
    mode: str = "regular"  # "regular" | "by_collection"
    priority_folder: Optional[str] = None
    # Off by default — see scripts/import_saved_instagram.py's
    # --reverse-collections docstring: purely a processing-order preference
    # now that real save dates come from all_posts_data, not a correctness
    # requirement.
    reverse_collections: bool = False


def _write_temp_json(data) -> Path:
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp)
        return Path(tmp.name)


def _validate_instagram_export_shapes(export_data, all_posts_data) -> None:
    """Structural validation, independent of the client — Pydantic's `Any`
    on export_data/all_posts_data only guarantees "valid JSON", not "the
    right shape". Raises HTTPException(400) with a specific, actionable
    message rather than silently writing garbage to disk and letting the
    import script discover the problem (or, worse, quietly find nothing
    and produce a no-op-looking run). Shared by both POST
    /instagram-export/preview and POST /instagram-export/jobs so neither
    route can be reached with an unvalidated file — including a direct API
    call that bypasses superbrain-web's own (also real, not just
    client-side) checks in its Next.js route handlers.
    """
    if not _ig_import.looks_like_collections_export(export_data):
        raise HTTPException(
            status_code=400,
            detail="That file doesn't look like an Instagram \"by collection\" export — expected "
                   "a JSON list of collections, each with a Name and a list of saved posts.",
        )
    if all_posts_data is not None and not _ig_import.looks_like_all_posts_export(all_posts_data):
        raise HTTPException(
            status_code=400,
            detail="That all-posts file doesn't look like an Instagram \"all posts\" export — "
                   "expected a flat JSON list of individually-saved posts, each with a URL and a "
                   "save timestamp.",
        )


def _instagram_export_preview(export_data, all_posts_data=None) -> dict:
    """Parse export_data the same way parse_export() would, without writing
    a permanent file — used by POST /instagram-export/preview so the web UI
    can sanity-check category counts before committing to an hours-long
    import job. When all_posts_data is also given, additionally reports how
    many of export_data's posts already have a known real save date in it."""
    tmp_path = _write_temp_json(export_data)
    try:
        records = _ig_import.parse_export(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    url_to_folders = _ig_import.group_by_url(records)
    folder_counts: Dict[str, int] = {}
    for folders in url_to_folders.values():
        for f in folders:
            folder_counts[f] = folder_counts.get(f, 0) + 1

    categories = [
        {"name": folder, "count": count}
        for folder, count in sorted(folder_counts.items(), key=lambda kv: -kv[1])
    ]
    result = {
        "categories": categories,
        "total_raw_entries": len(records),
        "total_unique_posts": len(url_to_folders),
    }

    if all_posts_data is not None:
        posts_tmp_path = _write_temp_json(all_posts_data)
        try:
            shortcode_ts = _ig_import.extract_post_timestamps(posts_tmp_path)
        finally:
            posts_tmp_path.unlink(missing_ok=True)
        known = sum(
            1 for url in url_to_folders
            if (code := _ig_import.shortcode_for(url)) and code in shortcode_ts
        )
        result["posts_with_known_date"] = known

    return result


def _run_instagram_export_job(
    job_id: str, json_path: Path, all_posts_json_path: Optional[Path], mode: str,
    priority_folder: Optional[str], reverse_collections: bool,
):
    """Spawns import_saved_instagram.py (or its _by_collection sibling) as a
    subprocess and streams its output into import_jobs.log_tail — same
    Popen shape as the /analyze inline subprocess spawn above, but run from
    a plain background thread (not asyncio.to_thread) since a full import
    can take hours, far past what's reasonable to hold a request thread
    open for. Started by POST /instagram-export/jobs, below.
    """
    db = get_db()
    script_name = (
        "import_saved_instagram_by_collection.py" if mode == "by_collection"
        else "import_saved_instagram.py"
    )
    cmd = [
        sys.executable, script_name, str(json_path),
        "--server-url", f"http://localhost:{API_SELF_PORT}",
        "--reverse-collections" if reverse_collections else "--no-reverse-collections",
    ]
    if mode == "by_collection" and priority_folder:
        cmd += ["--priority-folder", priority_folder]
    if all_posts_json_path:
        cmd += ["--all-posts-file", str(all_posts_json_path)]

    log_lines: List[str] = []

    def _persist_log():
        db.update_import_job(job_id, log_tail="".join(log_lines)[-_INSTAGRAM_EXPORT_LOG_MAX_CHARS:])

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(_INSTAGRAM_EXPORT_SCRIPTS_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            # PYTHONUNBUFFERED=1 is required here: without it, a child
            # Python process whose stdout is a pipe (not a TTY)
            # block-buffers, so the script's print() progress lines
            # wouldn't reach log_tail until the buffer filled or the
            # process exited — see _run_rescan_subprocess()'s docstring
            # above for the same issue.
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
            bufsize=1,
        )
        last_persist = time.time()
        for line in proc.stdout:
            log_lines.append(line)
            if time.time() - last_persist > 2:
                _persist_log()
                last_persist = time.time()
        proc.wait()
        _persist_log()

        now = datetime.utcnow().isoformat()
        if proc.returncode == 0:
            db.update_import_job(job_id, status="complete", finished_at=now)
        else:
            db.update_import_job(
                job_id, status="failed", finished_at=now,
                error=f"Script exited with code {proc.returncode}",
            )
    except Exception as e:
        logger.error(f"Instagram export job {job_id} failed to run: {e}")
        db.update_import_job(
            job_id, status="failed", finished_at=datetime.utcnow().isoformat(), error=str(e),
        )


@app.post("/instagram-export/preview")
async def preview_instagram_export(req: InstagramExportPreviewRequest, token: str = Depends(verify_token)):
    """
    Parse an uploaded Instagram "Download Your Information" export and
    return per-category post counts, without starting an import — lets
    superbrain-web's /import page show a sanity check (and populate the
    priority-folder dropdown for by-collection mode) before committing to a
    run that can take hours.

    Requires API authentication.
    """
    try:
        _validate_instagram_export_shapes(req.export_data, req.all_posts_data)
        preview = await asyncio.to_thread(_instagram_export_preview, req.export_data, req.all_posts_data)
        return {"success": True, **preview}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse export: {e}")


@app.post("/instagram-export/jobs")
async def create_instagram_export_job(req: InstagramExportJobCreate, token: str = Depends(verify_token)):
    """
    Kick off a background run of import_saved_instagram.py (mode=regular) or
    import_saved_instagram_by_collection.py (mode=by_collection, using
    priority_folder) against an uploaded export. Returns IMMEDIATELY with
    the created (status='running') job — the script runs for potentially
    hours (deliberately rate-limited, one /analyze call at a time), so this
    never blocks the request thread. Poll GET /instagram-export/jobs/{id}
    for status and a rolling log tail.

    Only one job may run at a time (409 otherwise) — both scripts share the
    same resumable scripts/import_state.json, which isn't safe for
    concurrent writers.

    Requires API authentication.
    """
    try:
        if req.mode not in {"regular", "by_collection"}:
            raise HTTPException(status_code=400, detail="mode must be 'regular' or 'by_collection'.")

        _validate_instagram_export_shapes(req.export_data, req.all_posts_data)

        db = get_db()
        for job in db.list_import_jobs(limit=5):
            if job["status"] == "running":
                raise HTTPException(status_code=409, detail="An import job is already running.")

        job_id = uuid.uuid4().hex
        _INSTAGRAM_EXPORT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = _INSTAGRAM_EXPORT_UPLOADS_DIR / f"{job_id}.json"
        json_path.write_text(json.dumps(req.export_data), encoding="utf-8")

        all_posts_json_path: Optional[Path] = None
        if req.all_posts_data is not None:
            all_posts_json_path = _INSTAGRAM_EXPORT_UPLOADS_DIR / f"{job_id}_posts.json"
            all_posts_json_path.write_text(json.dumps(req.all_posts_data), encoding="utf-8")

        job = db.create_import_job(
            job_id, req.mode, req.priority_folder, req.reverse_collections, json_path.name,
        )
        if not job:
            raise HTTPException(status_code=500, detail="Could not create the import job.")

        threading.Thread(
            target=_run_instagram_export_job,
            args=(job_id, json_path, all_posts_json_path, req.mode, req.priority_folder, req.reverse_collections),
            daemon=True,
        ).start()

        return {"success": True, "data": job}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/instagram-export/jobs")
async def list_instagram_export_jobs(token: str = Depends(verify_token)):
    """
    List recent Instagram-export import jobs, newest first.

    Requires API authentication.
    """
    try:
        db = get_db()
        jobs = db.list_import_jobs(limit=20)
        return {"success": True, "count": len(jobs), "data": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/instagram-export/jobs/{job_id}")
async def get_instagram_export_job(job_id: str, token: str = Depends(verify_token)):
    """
    Poll a single Instagram-export import job's status and log tail.

    Requires API authentication.
    """
    try:
        db = get_db()
        job = db.get_import_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found.")
        return {"success": True, "data": job}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/import")
async def import_data(
    data: dict,
    token: str = Depends(verify_token),
    mode: str = Query(default="merge", description="merge or replace")
):
    """
    Import data from JSON.
    - Requires API authentication
    - mode=merge: Add to existing data (skip duplicates by shortcode)
    - mode=replace: Replace all data (will clear database first)
    """
    return await _process_import_data(data, mode)

@app.post("/import/file")
async def import_data_file(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
    mode: str = Query(default="merge", description="merge or replace")
):
    """
    Import data from a ZIP or JSON file.
    - Requires API authentication
    - mode=merge or replace
    - Extracts thumbnails from ZIP archive if present
    """
    try:
        content = await file.read()
        
        # Check if it's a ZIP file
        if file.filename.endswith('.zip') or file.content_type == 'application/zip' or content.startswith(b'PK'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    # Look for superbrain_export.json or any json file
                    json_files = [name for name in z.namelist() if name.endswith('.json')]
                    
                    if not json_files:
                        raise HTTPException(status_code=400, detail="No JSON file found in the ZIP archive")
                    
                    # Prefer superbrain_export.json if it exists
                    target_file = "superbrain_export.json" if "superbrain_export.json" in json_files else json_files[0]
                    
                    with z.open(target_file) as f:
                        data = json.load(f)
                    
                    # Extract any custom image thumbnails from /thumbnails directory to the static folder mapped statically
                    thumbnails_dir = _STATIC_DIR / "thumbnails"
                    thumbnails_dir.mkdir(parents=True, exist_ok=True)
                    
                    for name in z.namelist():
                        if name.startswith("thumbnails/") and not name.endswith("/"):
                            img_filename = name.split("/")[-1]
                            with z.open(name) as zf, open(thumbnails_dir / img_filename, "wb") as out_f:
                                out_f.write(zf.read())
                                
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Invalid ZIP file")
        else:
            # Assume it's a direct JSON file
            try:
                data = json.loads(content.decode('utf-8'))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON file")
                
        return await _process_import_data(data, mode)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing import file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

async def _process_import_data(data: dict, mode: str):
    try:
        # Validate input data structure
        validated = ImportData.model_validate(data)

        if mode not in {"merge", "replace"}:
            raise HTTPException(status_code=400, detail="Invalid import mode. Use 'merge' or 'replace'.")

        db = get_db()

        imported_posts = 0
        skipped_posts = 0

        # Handle mode=replace
        if mode == "replace":
            logger.warning("Import mode=replace: clearing database first")
            conn = db._conn
            conn.execute("DELETE FROM analyses")
            conn.execute("DELETE FROM collections")
            conn.execute("DELETE FROM processing_queue")
            # Ensure the permanently-seeded collections exist even if import has none
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ('default_watch_later', 'Watch Later', 'time', '[]', now, now)
            )
            conn.execute(
                "INSERT INTO collections (id, name, icon, post_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ('iphone_shares', 'iPhone', '📱', '[]', now, now)
            )
            conn.commit()

        # Import posts - validate and filter allowed fields
        posts = validated.posts or []
        for post in posts:
            shortcode = post.get("shortcode")
            if not shortcode:
                continue

            # Filter to only allowed fields (prevent arbitrary field injection)
            filtered_post = {k: v for k, v in post.items() if k in ALLOWED_POST_FIELDS}

            # Check if exists (for merge mode)
            existing = db.check_cache(shortcode)
            if existing and mode == "merge":
                skipped_posts += 1
                continue

            db.save_analysis(
                shortcode=shortcode,
                url=filtered_post.get("url", ""),
                username=filtered_post.get("username", ""),
                title=filtered_post.get("title", ""),
                summary=filtered_post.get("summary", ""),
                tags=filtered_post.get("tags", []),
                music=filtered_post.get("music", ""),
                category=filtered_post.get("category", "other"),
                language=filtered_post.get("language", ""),
                media_files=filtered_post.get("media_files", []),
                visual_analysis=filtered_post.get("visual_analysis", ""),
                audio_transcription=filtered_post.get("audio_transcription", ""),
                text_analysis=filtered_post.get("text_analysis", ""),
                likes=filtered_post.get("likes", 0),
                post_date=filtered_post.get("post_date"),
                content_type=filtered_post.get("content_type", "instagram"),
                thumbnail=filtered_post.get("thumbnail", ""),
                # Preserve the imported post's own version rather than
                # stamping it current — a restored backup wasn't actually
                # re-run through today's pipeline.
                analysis_version=filtered_post.get("analysis_version", 0),
            )
            imported_posts += 1

        # Import collections - validate and filter allowed fields
        collections = validated.collections or []
        imported_collections = 0
        for coll in collections:
            coll_id = coll.get("id")
            if not coll_id:
                continue

            post_ids = coll.get("post_ids")
            if post_ids is None:
                post_ids = coll.get("postIds", [])

            db.upsert_collection(
                collection_id=coll_id,
                name=coll.get("name", "Untitled"),
                icon=coll.get("icon", "folder"),
                post_ids=post_ids if isinstance(post_ids, list) else [],
                created_at=coll.get("created_at") or coll.get("createdAt"),
                updated_at=coll.get("updated_at") or coll.get("updatedAt"),
            )
            imported_collections += 1

        logger.info(f"📥 Import complete: {imported_posts} posts, {skipped_posts} skipped, {imported_collections} collections")

        return {
            "success": True,
            "imported_posts": imported_posts,
            "skipped_posts": skipped_posts,
            "imported_collections": imported_collections,
            "mode": mode
        }
    except Exception as e:
        logger.error(f"Error importing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Settings endpoints for AI Providers and Instagram configuration
# These manage the .api_keys file and dynamically update the ModelRouter

class ProviderKeyUpdate(BaseModel):
    provider: str
    api_key: str

class InstagramCredentials(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    sessionid: Optional[str] = None

def get_config_path(filename: str) -> Path:
    """Get path to config directory files."""
    return Path(__file__).parent / "config" / filename

@app.get("/settings/ai-providers")
async def get_ai_providers(token: str = Depends(verify_token)):
    """
    Get available AI providers and their key status.
    - Requires API authentication
    """
    from core.model_router import get_router
    router = get_router()
    providers = router.get_available_providers()
    
    return {
        "success": True,
        "providers": {
            "groq": {
                "name": "Groq",
                "has_key": providers.get("groq", False),
                "key_hint": "gsk_..." if providers.get("groq") else None
            },
            "gemini": {
                "name": "Google Gemini",
                "has_key": providers.get("gemini", False),
                "key_hint": "AIza..." if providers.get("gemini") else None
            },
            "openrouter": {
                "name": "OpenRouter",
                "has_key": providers.get("openrouter", False),
                "key_hint": "sk-or-..." if providers.get("openrouter") else None
            },
            "ollama": {
                "name": "Ollama (Local)",
                "has_key": providers.get("ollama", False),
                "key_hint": None
            }
        }
    }

@app.post("/settings/ai-providers")
async def set_ai_provider_key(
    data: ProviderKeyUpdate,
    token: str = Depends(verify_token)
):
    """
    Set an API key for an AI provider.
    - Requires API authentication
    - provider: groq, gemini, or openrouter
    """
    from core.model_router import get_router
    import httpx
    
    valid_providers = ["groq", "gemini", "openrouter"]
    provider_slug = data.provider.lower()
    if provider_slug not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )
    
    if not data.api_key or len(data.api_key.strip()) < 5:
        raise HTTPException(status_code=400, detail="Invalid API key format")
        
    # Validate API key explicitly
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider_slug == "groq":
                resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {data.api_key.strip()}"})
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid Groq API Key")
            elif provider_slug == "gemini":
                resp = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={data.api_key.strip()}")
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid Gemini API Key")
            elif provider_slug == "openrouter":
                resp = await client.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {data.api_key.strip()}"})
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid OpenRouter API Key")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error validating API key: {e}")
    
    router = get_router()
    success = router.set_api_key(data.provider.lower(), data.api_key.strip())
    
    if success:
        logger.info(f"🔑 API key updated for {data.provider}")
        return {"success": True, "provider": data.provider, "message": "API key updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save API key")

@app.delete("/settings/ai-providers/{provider}")
async def delete_ai_provider_key(
    provider: str,
    token: str = Depends(verify_token)
):
    """
    Delete an API key for an AI provider.
    - Requires API authentication
    """
    from core.model_router import get_router
    
    valid_providers = ["groq", "gemini", "openrouter"]
    if provider.lower() not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )
    
    router = get_router()
    success = router.delete_api_key(provider.lower())
    
    if success:
        logger.info(f"🔑 API key deleted for {provider}")
        return {"success": True, "provider": provider, "message": "API key deleted"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete API key")

@app.get("/settings/instagram")
async def get_instagram_credentials(token: str = Depends(verify_token)):
    """
    Get Instagram credentials (masked).
    - Requires API authentication
    """
    api_keys_file = get_config_path(".api_keys")
    
    username = None
    has_password = False
    
    if api_keys_file.exists():
        with open(api_keys_file, "r") as f:
            for line in f:
                if line.startswith("INSTAGRAM_USERNAME="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("INSTAGRAM_PASSWORD="):
                    has_password = bool(line.split("=", 1)[1].strip())
    
    return {
        "success": True,
        "configured": username is not None and username != "",
        "username": username if username else None,
        "has_password": has_password
    }

@app.post("/settings/instagram")
async def set_instagram_credentials(
    data: InstagramCredentials,
    token: str = Depends(verify_token)
):
    """
    Set Instagram credentials.
    - Requires API authentication
    """
    sessionid = getattr(data, "sessionid", None)
    
    if not sessionid and (not data.username or not data.password):
        raise HTTPException(status_code=400, detail="Either login (username + password) OR Session ID is required")
        
    username_to_use = data.username or "session_user"
    
    api_keys_file = get_config_path(".api_keys")
    
    # Authenticate with Instagram first
    try:
        import instaloader
        L = instaloader.Instaloader()
        session_file = Path(__file__).parent / ".instaloader_session"
        if sessionid:
            L.context._session.cookies.set("sessionid", sessionid, domain=".instagram.com")
            L.context.username = username_to_use
            # To verify sessionid, attempt to get a profile to see if block is lifted
            try:
                L.get_profile("instagram")
            except Exception:
                # Some sessionids might have minor issues fetching profiles but work for posts, 
                # but getting "instagram" is generally safe. Ignore non-fatal if possible
                pass
        else:
            L.login(data.username, data.password)
            username_to_use = data.username
            
        L.save_session_to_file(str(session_file))
        logger.info(f"🍪 Instagram session successfully verified and saved for {username_to_use}")
    except instaloader.exceptions.BadCredentialsException:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        raise HTTPException(status_code=401, detail="Two-factor auth blocked login. Please use Session ID cookie instead.")
    except instaloader.exceptions.ConnectionException as e:
        error_msg = str(e).lower()
        if "checkpoint" in error_msg or "challenge" in error_msg:
            raise HTTPException(status_code=401, detail="Instagram Checkpoint block. Please use Session ID cookie instead.")
        raise HTTPException(status_code=400, detail=f"Instagram connection error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to authenticate with Instagram: {e}")

    # Read existing content
    lines = []
    username_found = False
    password_found = False
    
    if api_keys_file.exists():
        with open(api_keys_file, "r") as f:
            for line in f:
                if line.startswith("INSTAGRAM_USERNAME="):
                    lines.append(f"INSTAGRAM_USERNAME={username_to_use}\n")
                    username_found = True
                elif line.startswith("INSTAGRAM_PASSWORD="):
                    if data.password:
                        lines.append(f"INSTAGRAM_PASSWORD={data.password}\n")
                    else:
                        lines.append("INSTAGRAM_PASSWORD=\n")
                    password_found = True
                else:
                    lines.append(line)
    
    if not username_found:
        lines.append(f"INSTAGRAM_USERNAME={username_to_use}\n")
    if not password_found:
        if data.password:
            lines.append(f"INSTAGRAM_PASSWORD={data.password}\n")
        else:
            lines.append("INSTAGRAM_PASSWORD=\n")
    
    with open(api_keys_file, "w") as f:
        f.writelines(lines)
        
    logger.info(f"📸 Instagram credentials updated for {username_to_use}")
    
    return {
        "success": True,
        "username": username_to_use,
        "message": "Instagram credentials updated"
    }

@app.delete("/settings/instagram")
async def delete_instagram_credentials(token: str = Depends(verify_token)):
    """
    Delete Instagram credentials.
    - Requires API authentication
    """
    api_keys_file = get_config_path(".api_keys")
    
    if api_keys_file.exists():
        lines = []
        with open(api_keys_file, "r") as f:
            for line in f:
                if not line.startswith("INSTAGRAM_USERNAME=") and not line.startswith("INSTAGRAM_PASSWORD="):
                    lines.append(line)
        
        with open(api_keys_file, "w") as f:
            f.writelines(lines)
    
    logger.info("📸 Instagram credentials deleted")
    
    return {"success": True, "message": "Instagram credentials deleted"}


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting SuperBrain API...")
    print(f"📖 API Docs: http://localhost:{API_SELF_PORT}/docs")
    print(f"🔍 Interactive: http://localhost:{API_SELF_PORT}/redoc")
    uvicorn.run("api:app", host="0.0.0.0", port=API_SELF_PORT, reload=False)
