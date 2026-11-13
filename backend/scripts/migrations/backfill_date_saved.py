#!/usr/bin/env python3
"""
Backfill analyses.date_saved for Instagram posts already in the database,
using saved_posts.json — Instagram's flat "every individually-saved post"
export, where each entry carries its own real `timestamp`.

Unlike the old saved_order backfill (retired — see the migration comment in
core/database.py), this needs no collection grouping or reversal logic:
saved_posts.json already has a real per-post timestamp directly, verified
to be the actual save date (always later than the post's own publish date,
by a wildly varying amount — see the date_saved migration comment).

Reuses import_saved_instagram.py's extract_post_timestamps() and
shortcode_for() (sibling-module import, same trick
import_saved_instagram_by_collection.py already uses) rather than
re-parsing the flat-list shape from scratch.

Usage:
    cd backend
    .venv/bin/python scripts/migrations/backfill_date_saved.py saved_posts.json --dry-run
    .venv/bin/python scripts/migrations/backfill_date_saved.py saved_posts.json
    .venv/bin/python scripts/migrations/backfill_date_saved.py saved_posts.json --force
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.database import get_db
from import_saved_instagram import extract_post_timestamps


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    dry_run = "--dry-run" in args
    positional = [a for a in args if not a.startswith("--")]

    if not positional:
        print("Usage: python scripts/migrations/backfill_date_saved.py <saved_posts.json> [--force] [--dry-run]")
        sys.exit(1)

    all_posts_path = Path(positional[0])
    if not all_posts_path.exists():
        print(f"[ERROR] Path not found: {all_posts_path}")
        sys.exit(1)

    shortcode_ts = extract_post_timestamps(all_posts_path)
    print(f"Parsed {len(shortcode_ts)} save timestamp(s) from {all_posts_path}.")

    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    cur = db._conn.cursor()
    cur.execute("SELECT shortcode, date_saved FROM analyses WHERE content_type = 'instagram'")
    existing = {row["shortcode"]: row["date_saved"] for row in cur.fetchall()}

    updated = already_set = not_found = 0

    for shortcode, iso_date in shortcode_ts.items():
        if shortcode not in existing:
            not_found += 1
            continue
        if existing[shortcode] is not None and not force:
            already_set += 1
            continue

        if dry_run:
            updated += 1
            continue

        if db.update_date_saved(shortcode, iso_date):
            updated += 1
        else:
            print(f"[WARNING] Failed to update date_saved for {shortcode}")

    print(
        f"\n{'[dry-run] Would update' if dry_run else 'Done.'} "
        f"{updated} updated, {already_set} already had date_saved (skipped), "
        f"{not_found} not found in DB."
    )


if __name__ == "__main__":
    main()
