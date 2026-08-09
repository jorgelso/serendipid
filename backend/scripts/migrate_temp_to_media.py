#!/usr/bin/env python3
"""
One-time migration: relocate already-downloaded post media sitting in
temp/<caption-folder>/ into the permanent media/<shortcode>/ store, and
record the result on each post's DB row.

Only touches a temp folder when its shortcode (parsed from info.txt) maps to
exactly one existing DB row that doesn't already have media_files recorded.
Anything ambiguous or unrecoverable (no info.txt, no matching DB row) is
skipped and reported, never guessed.

Usage:
    cd backend
    .venv/bin/python scripts/migrate_temp_to_media.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from core.media_store import relocate_to_media_store

TEMP_DIR = Path(__file__).resolve().parent.parent / "temp"

_IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def main() -> None:
    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    if not TEMP_DIR.exists():
        print("No temp/ directory — nothing to migrate.")
        return

    db_rows = {p["shortcode"]: p["media_files"] for p in db.get_all_posts()}

    folder_to_shortcode = {}
    skipped_no_info = []
    for folder in sorted(TEMP_DIR.iterdir()):
        if not folder.is_dir():
            continue
        info = folder / "info.txt"
        if not info.exists():
            skipped_no_info.append(folder.name)
            continue
        text = info.read_text(encoding="utf-8", errors="ignore")
        m = _IG_URL_RE.search(text)
        if not m:
            skipped_no_info.append(folder.name)
            continue
        folder_to_shortcode[folder] = m.group(1)

    # Guard against ambiguity: two folders mapping to the same shortcode.
    from collections import Counter
    sc_counts = Counter(folder_to_shortcode.values())
    ambiguous = {sc for sc, c in sc_counts.items() if c > 1}

    migrated, skipped_no_db_row, skipped_ambiguous, skipped_already_has_media, failed = [], [], [], [], []

    for folder, shortcode in folder_to_shortcode.items():
        if shortcode in ambiguous:
            skipped_ambiguous.append((folder.name, shortcode))
            continue
        if shortcode not in db_rows:
            skipped_no_db_row.append((folder.name, shortcode))
            continue
        existing = db_rows[shortcode]
        if existing:
            skipped_already_has_media.append(shortcode)
            continue

        print(f"[{shortcode}] relocating from '{folder.name}'...", end=" ", flush=True)
        try:
            media_files = relocate_to_media_store(str(folder), shortcode)
        except Exception as e:
            print(f"FAILED ({e})")
            failed.append((shortcode, str(e)))
            continue

        if not media_files:
            print("FAILED (no files relocated)")
            failed.append((shortcode, "no files relocated"))
            continue

        ok = db.update_post(shortcode, {"media_files": media_files})
        if ok:
            print(f"OK ({len(media_files)} files)")
            migrated.append(shortcode)
        else:
            print("FAILED (DB update failed — files were moved, rerun script to retry linking)")
            failed.append((shortcode, "db update failed"))

    print()
    print("=" * 70)
    print(f"Migrated:                  {len(migrated)}")
    print(f"Skipped (no info.txt):     {len(skipped_no_info)}  {skipped_no_info}")
    print(f"Skipped (no DB row):       {len(skipped_no_db_row)}  {skipped_no_db_row}")
    print(f"Skipped (ambiguous):       {len(skipped_ambiguous)}  {skipped_ambiguous}")
    print(f"Skipped (already had media): {len(skipped_already_has_media)}  {skipped_already_has_media}")
    print(f"Failed:                    {len(failed)}  {failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()
