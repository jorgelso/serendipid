#!/usr/bin/env python3
"""
Backfill analyses.saved_order for Instagram posts already in the database
that were bulk-imported from an Instagram "Download Your Information" JSON
export (via import_saved_instagram.py / import_saved_instagram_by_collection.py).

Those posts all have analyzed_at stamped at whatever real-world moment the
import script happened to process them, not when they were actually saved
on Instagram — a bulk import run compresses hundreds/thousands of saves
into a handful of days. The export JSON has no per-post timestamp, but
within each collection Instagram lists posts newest-saved-first, so that
relative order is the only chronology signal available.

This reuses import_saved_instagram.py's parse_export() and
reverse_within_collections() (same reasoning as that script's
--reverse-collections flag) to reconstruct each collection's oldest-first
order, then walks every collection (in the arbitrary order they appear in
the export file — collections are NOT unified against each other, only
each one's own internal order is corrected) assigning a strictly increasing
rank. A post saved into more than one collection keeps whichever rank it
gets from the first collection it's encountered in (matching
group_by_url()'s existing first-seen dedup semantics elsewhere in this
codebase).

saved_order is intentionally NOT a date — see the migration comment above
ALTER TABLE analyses ADD COLUMN saved_order in core/database.py.

Usage:
    cd backend
    .venv/bin/python scripts/backfill_saved_order.py saved_collections.json --dry-run
    .venv/bin/python scripts/backfill_saved_order.py saved_collections.json
    .venv/bin/python scripts/backfill_saved_order.py saved_collections.json --force
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db
from import_saved_instagram import parse_export, reverse_within_collections, shortcode_for


def build_shortcode_ranks(export_path: Path) -> dict:
    """Returns {shortcode: rank} — rank 1 is the oldest reconstructed save."""
    records = parse_export(export_path)
    reversed_records = reverse_within_collections(records)

    ranks: dict = {}
    rank = 1
    for _folder, url, _caption, _hashtags in reversed_records:
        code = shortcode_for(url)
        if not code or code in ranks:
            continue
        ranks[code] = rank
        rank += 1
    return ranks


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    dry_run = "--dry-run" in args
    positional = [a for a in args if not a.startswith("--")]

    if not positional:
        print("Usage: python scripts/backfill_saved_order.py <export.json> [--force] [--dry-run]")
        sys.exit(1)

    export_path = Path(positional[0])
    if not export_path.exists():
        print(f"[ERROR] Path not found: {export_path}")
        sys.exit(1)

    ranks = build_shortcode_ranks(export_path)
    print(f"Reconstructed order for {len(ranks)} unique shortcode(s) from {export_path}.")

    db = get_db()
    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    cur = db._conn.cursor()
    cur.execute("SELECT shortcode, saved_order FROM analyses WHERE content_type = 'instagram'")
    existing = {row["shortcode"]: row["saved_order"] for row in cur.fetchall()}

    updated = already_set = not_found = 0

    for shortcode, rank in ranks.items():
        if shortcode not in existing:
            not_found += 1
            continue
        if existing[shortcode] is not None and not force:
            already_set += 1
            continue

        if dry_run:
            updated += 1
            continue

        if db.update_saved_order(shortcode, rank):
            updated += 1
        else:
            print(f"[WARNING] Failed to update saved_order for {shortcode}")

    print(
        f"\n{'[dry-run] Would update' if dry_run else 'Done.'} "
        f"{updated} updated, {already_set} already had saved_order (skipped), "
        f"{not_found} not found in DB."
    )


if __name__ == "__main__":
    main()
