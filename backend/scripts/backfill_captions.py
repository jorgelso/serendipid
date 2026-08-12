#!/usr/bin/env python3
"""
Backfill raw Instagram captions for existing posts.

The live pipeline (main.py) now parses the caption instaloader scraped into
media/<shortcode>/info.txt at analysis time and saves it to analyses.caption.
Posts analyzed before that existed still have their caption sitting on disk
in info.txt (relocated there by core.media_store.relocate_to_media_store)
but never had it written to the DB. This script recovers it from those
already-downloaded files — no re-download, no LLM calls, pure regex parse.

Posts with no info.txt (never downloaded, or imported outside the normal
main.py pipeline) are skipped, not treated as errors. Posts with a
non-empty caption already are skipped by default.

Usage:
    cd backend
    .venv/bin/python scripts/backfill_captions.py            # only posts missing a caption
    .venv/bin/python scripts/backfill_captions.py --force     # re-parse every Instagram post
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.media_store import MEDIA_DIR

CAPTION_RE = re.compile(r'Caption:\n-+\n(.*?)\n-+\n', re.DOTALL)


def extract_caption(info_path: Path) -> str:
    content = info_path.read_text(encoding='utf-8')
    match = CAPTION_RE.search(content)
    if not match:
        return ""
    text = match.group(1).strip()
    return "" if text == "No caption" else text


def main() -> None:
    force = "--force" in sys.argv

    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    cur = db._conn.cursor()
    cur.execute("SELECT shortcode, caption FROM analyses WHERE content_type = 'instagram'")
    rows = cur.fetchall()

    candidates = [r for r in rows if force or not r["caption"]]
    print(
        f"{len(rows)} Instagram post(s) total; "
        f"{len(candidates)} {'(re-parsing all)' if force else 'missing a caption'}."
    )

    if not candidates:
        print("Nothing to backfill.")
        return

    ok = no_file = no_caption = fail = 0
    for i, row in enumerate(candidates, start=1):
        shortcode = row["shortcode"]
        print(f"[{i}/{len(candidates)}] {shortcode} ...", end=" ", flush=True)

        info_path = MEDIA_DIR / shortcode / "info.txt"
        if not info_path.exists():
            no_file += 1
            print("SKIP (no info.txt)")
            continue

        try:
            caption = extract_caption(info_path)
        except Exception as e:
            fail += 1
            print(f"FAILED ({e})")
            continue

        if not caption:
            no_caption += 1
            print("SKIP (no caption found)")
            continue

        if db.update_caption(shortcode, caption):
            ok += 1
            print(f"OK ({len(caption)} chars)")
        else:
            fail += 1
            print("FAILED (db write error)")

    print(
        f"\nDone. {ok} updated, {no_file} skipped (no info.txt), "
        f"{no_caption} skipped (no caption in info.txt), {fail} failed."
    )


if __name__ == "__main__":
    main()
