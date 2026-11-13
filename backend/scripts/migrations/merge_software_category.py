#!/usr/bin/env python3
"""
One-off backfill: merge the legacy "software" category label into its
canonical replacement "software & tech".

"software" was the pre-taxonomy-overhaul (analysis_version 0) label; the
overhaul (version 1) renamed it to "software & tech" going forward, but
never rewrote already-saved rows, so both labels ended up coexisting as
distinct categories in the same library.

Does NOT re-run AI analysis or touch any other field — it only rewrites the
category list on affected rows, deduplicating if a post somehow already
carries both labels.

Usage:
    cd backend
    .venv/bin/python scripts/migrations/merge_software_category.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.database import get_db

LEGACY_LABEL = "software"
CANONICAL_LABEL = "software & tech"


def main() -> None:
    db = get_db()

    if not db.is_connected():
        print("[ERROR] Could not connect to database.")
        sys.exit(1)

    cur = db._conn.execute(
        "SELECT shortcode, category FROM analyses WHERE category LIKE ?",
        (f'%{LEGACY_LABEL}%',),
    )
    rows = cur.fetchall()

    updated = 0
    for row in rows:
        shortcode = row["shortcode"]
        raw = row["category"]
        try:
            import json
            parsed = json.loads(raw)
            categories = parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            categories = [raw] if raw else []

        if LEGACY_LABEL not in categories:
            continue

        merged = []
        for c in categories:
            label = CANONICAL_LABEL if c == LEGACY_LABEL else c
            if label not in merged:
                merged.append(label)

        db.update_post(shortcode, {"category": merged})
        updated += 1
        print(f"  {shortcode}: {categories} -> {merged}")

    print(f"\nMerged '{LEGACY_LABEL}' into '{CANONICAL_LABEL}' on {updated} post(s).")


if __name__ == "__main__":
    main()
