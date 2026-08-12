#!/usr/bin/env python3
"""
Throwaway test for the neuroscience/self-improvement tutorial-format carve-out
in core/eloquence.py's rubric (criterion 1). Print-only — does NOT write to
the database.

Usage:
    cd backend
    .venv/bin/python scripts/test_carveout.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.eloquence import build_eloquence_prompt, parse_eloquence
from core.model_router import get_router

SHORTCODES = ["DTVOiUeCgEv", "DVRBkdQiptX", "DR2MBXOCpfN"]
MODEL_ID = "gpt-4.1"


def main() -> None:
    db = get_db()
    router = get_router()

    for shortcode in SHORTCODES:
        post = db.check_cache(shortcode)
        if not post:
            print(f"[SKIP] {shortcode} not found")
            continue

        title = post.get("title", "")
        transcript = post.get("audio_transcription", "")
        prompt = build_eloquence_prompt(transcript)

        try:
            raw = router._openai_text(MODEL_ID, prompt)
        except Exception as e:
            print(f"[ERROR] {shortcode}: {e}")
            continue

        is_eloquent, is_tutorial, rationale = parse_eloquence(raw)
        verdict = "YES" if is_eloquent else ("NO" if is_eloquent is False else "UNPARSEABLE")

        print(f"\n{'=' * 100}")
        print(f"{shortcode} — {title}")
        print(f"VERDICT: {verdict}")
        print(f"RATIONALE: {rationale}")


if __name__ == "__main__":
    main()
