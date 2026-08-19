#!/usr/bin/env python3
"""
Pure decision logic for the rescan pipeline (see scripts/rescan_post.py):
given an existing `analyses` row, decide which analyzer steps actually need
to be redone, versus which can be reused as-is. See backend/CLAUDE.md's
"Rescan pipeline" section for the full picture — the short version is that
almost no rescan needs to touch Instagram at all, and most don't need to
re-run every analyzer either.
"""

from dataclasses import dataclass, field
from pathlib import Path

from core.rescan_dates import (
    VISUAL_PROMPT_REWRITE_CUTOFF,
    VISUAL_FRAME_SAMPLING_CUTOFF,
    AUDIO_TRANSCRIBE_FAILURE_FIX_CUTOFF,
    older_than,
)
from core.media_store import MEDIA_DIR

# The one version gap that's fixable with nothing but a re-score — no
# summary rebuild, no analyzer re-runs, no redownload. Currently just the
# 7->8 importance-rubric fix; extend this set if a future version bump is
# ever similarly cheap (e.g. another importance-only or embedding-only fix).
IMPORTANCE_ONLY_VERSIONS = {7}


@dataclass
class RescanPlan:
    shortcode: str
    cheap_importance_only: bool
    redo_visual: bool
    redo_audio: bool          # also covers analyzers/music_identifier.py
    needs_redownload: bool
    reasons: list = field(default_factory=list)


def _media_dir_has(shortcode: str, *suffixes: str) -> bool:
    d = MEDIA_DIR / shortcode
    if not d.is_dir():
        return False
    return any(f.suffix.lower() in suffixes for f in d.iterdir() if f.is_file())


def decide_rescan_plan(row: dict) -> RescanPlan:
    shortcode = row["shortcode"]
    reasons = []

    if row.get("analysis_version") in IMPORTANCE_ONLY_VERSIONS:
        return RescanPlan(
            shortcode=shortcode, cheap_importance_only=True,
            redo_visual=False, redo_audio=False, needs_redownload=False,
            reasons=["stamped version is importance-only gap to current"],
        )

    analyzed_at = row.get("analyzed_at")

    redo_visual = older_than(analyzed_at, VISUAL_PROMPT_REWRITE_CUTOFF) or \
        older_than(analyzed_at, VISUAL_FRAME_SAMPLING_CUTOFF)
    if redo_visual:
        reasons.append("visual_analyze.py prompt/frame-sampling changed since analyzed_at")

    has_audio = bool(row.get("audio_transcription")) or any(
        f.lower().endswith((".mp3",)) for f in (row.get("media_files") or [])
    )
    redo_audio = (
        has_audio
        and older_than(analyzed_at, AUDIO_TRANSCRIBE_FAILURE_FIX_CUTOFF)
        and not row.get("transcription_backend")
    )
    if redo_audio:
        reasons.append("audio predates the transcription-failure-silencing fix, unverified")

    needs_redownload = False
    if redo_visual and not _media_dir_has(shortcode, ".mp4", ".jpg"):
        needs_redownload = True
        reasons.append("no local video/image in media/<shortcode>/ for visual re-run")
    if redo_audio and not _media_dir_has(shortcode, ".mp3", ".mp4"):
        needs_redownload = True
        reasons.append("no local audio/video in media/<shortcode>/ for audio re-run")

    return RescanPlan(
        shortcode=shortcode, cheap_importance_only=False,
        redo_visual=redo_visual, redo_audio=redo_audio,
        needs_redownload=needs_redownload, reasons=reasons,
    )
