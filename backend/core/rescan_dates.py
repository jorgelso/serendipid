#!/usr/bin/env python3
"""
Dated cutoffs for the rescan pipeline's version-gap-aware step selection
(see core/rescan_plan.py). Each constant marks the UTC moment a specific
Instagram analyzer's prompt/behavior changed — a post whose `analyzed_at`
predates a cutoff was analyzed under the old behavior and needs that
specific analyzer re-run; a post analyzed after it already reflects the
current behavior and can skip that step.

`analyzed_at` is stored as `datetime.utcnow().isoformat()` (core/database.py),
so every cutoff here is UTC, converted from the commit's local -06:00
timestamp (`git show -s --format=%ci <hash>`) — don't compare against a
naive local-time reading of the commit log.

Add a new cutoff here whenever an analyzer prompt changes again, and wire it
into core/rescan_plan.py's decide_rescan_plan().
"""

from datetime import datetime

# analyzers/visual_analyze.py — VISION_PROMPT rewritten from a concise
# 5-bullet thematic summary to a detailed verbatim-extraction prompt.
# Commit 1e48609, 2026-08-08 13:31:39 -06:00.
VISUAL_PROMPT_REWRITE_CUTOFF = datetime(2026, 8, 8, 19, 31, 39)

# analyzers/visual_analyze.py — frame sampling changed from a fixed 4 frames
# to duration-scaled 4-13 frames (_frame_count_for_duration()). NOT tied to
# any analysis_version bump — analyzed_at is the only way to detect this.
# Commit 197495e, 2026-08-09 13:19:36 -06:00.
VISUAL_FRAME_SAMPLING_CUTOFF = datetime(2026, 8, 9, 19, 19, 36)

# analyzers/audio_transcribe.py — fixed a bug where total transcription
# failure (Groq Whisper + local Whisper both failing) silently returned
# success with the printed error text stored as if it were the transcript.
# Same commit added the `transcription_backend` column, which is why an
# empty transcription_backend on a post with audio is used as a secondary
# signal (see core/rescan_plan.py) — analyzed_at alone can't fully
# distinguish "predates the fix" from "postdates it but the column wasn't
# backfilled," so both checks are used together.
# Commit 1cb054b, 2026-08-10 14:02:14 -06:00.
AUDIO_TRANSCRIBE_FAILURE_FIX_CUTOFF = datetime(2026, 8, 10, 20, 2, 14)


def older_than(analyzed_at: str | None, cutoff: datetime) -> bool:
    """True if `analyzed_at` (an ISO timestamp string, as stored by
    core/database.py) predates `cutoff`. A missing/unparseable timestamp is
    treated as older than everything — when in doubt, prefer redoing the
    step over silently skipping it."""
    if not analyzed_at:
        return True
    try:
        return datetime.fromisoformat(analyzed_at) < cutoff
    except ValueError:
        return True
