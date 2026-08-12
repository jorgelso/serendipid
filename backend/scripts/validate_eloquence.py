#!/usr/bin/env python3
"""
One-off validation run for the eloquence rubric (core/eloquence.py) against a
hand-labeled set of posts, before wiring this into a real backfill/column.

Does NOT write anything to the database — prints each post's title, the
human label, and the LLM's verdict + rationale side by side so the rubric
can be judged before it's trusted to score the full library.

Usage:
    cd backend
    .venv/bin/python scripts/validate_eloquence.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.eloquence import build_eloquence_prompt, parse_eloquence
from core.model_router import get_router

LABELED = [
    ("DSlUwqnkigj", "good", "Financial nihilism commentary"),
    ("DahNp8bgYqs", "good", "Graduation speech"),
    ("Da5p1Gxtk6i", "good", "Ancient Rome parallels"),
    ("DY-GAhOtjnU", "good", "How to Corrupt a Democracy"),
    ("DX2ByDPR8lq", "good", "Authoritarian Playbook"),
    ("DUD_rNaEbat", "bad", "GCP red-team walkthrough"),
    ("DYidSQSAdUf", "bad", "Internship return offer"),
    ("DJRd3jeoA7d", "bad", "Google Dorking for OSINT"),
    ("DQ3P1pMETjg", "bad", "Unethical side quests"),
]

MODEL_ID = "gpt-4.1"


def main() -> None:
    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    router = get_router()

    correct = 0
    total = 0
    rows = []

    for shortcode, label, short_title in LABELED:
        post = db.check_cache(shortcode)
        if not post:
            print(f"[SKIP] {shortcode} not found in DB")
            continue

        transcript = post.get("audio_transcription", "")
        prompt = build_eloquence_prompt(transcript)

        try:
            raw = router._openai_text(MODEL_ID, prompt)
        except Exception as e:
            print(f"[ERROR] {shortcode} ({short_title}): {e}")
            continue

        is_eloquent, is_tutorial, rationale = parse_eloquence(raw)
        llm_verdict = "good" if is_eloquent else ("bad" if is_eloquent is False else "UNPARSEABLE")
        match = "✓" if llm_verdict == label else "✗"
        if llm_verdict == label:
            correct += 1
        total += 1

        if is_eloquent is not None:
            db.update_eloquence(shortcode, is_eloquent, rationale, is_tutorial=is_tutorial)

        rows.append((shortcode, short_title, label, llm_verdict, match, rationale))

    print("\n" + "=" * 100)
    for shortcode, short_title, label, llm_verdict, match, rationale in rows:
        print(f"\n[{match}] {shortcode} — {short_title}")
        print(f"    human label: {label:5}   llm verdict: {llm_verdict}")
        print(f"    rationale: {rationale}")
    print("\n" + "=" * 100)
    print(f"\n{correct}/{total} matched the human label.")


if __name__ == "__main__":
    main()
