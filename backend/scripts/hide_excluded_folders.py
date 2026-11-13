#!/usr/bin/env python3
"""
One-time cleanup for Instagram folders that are never stored
(excluded_import_folders in the config, see core/app_config.py),
for posts imported before that rule existed.

For each excluded collection row:
  - posts that are in no other collection are hidden (soft-deleted via
    db.delete_post(): is_hidden=1 + deleted_log, so the data is kept, clients
    drop them on sync, and a re-import gets a 410 instead of re-adding them);
  - posts that are also in another collection are left visible;
  - the collection row itself is deleted.

Hidden posts can be brought back individually with db.restore_post(shortcode)
or POST /analyze with restore=true.

Usage:
    python scripts/hide_excluded_folders.py           # dry run, prints what it would do
    python scripts/hide_excluded_folders.py --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db  # noqa: E402
from core.sensitive import is_excluded_folder  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="Actually hide posts and delete the collection rows")
    args = p.parse_args()

    db = get_db()
    collections = db.get_collections()
    excluded = [c for c in collections if is_excluded_folder(c.get("name"))]
    if not excluded:
        print("No excluded-folder collections found — nothing to do.")
        return

    for coll in excluded:
        others = set()
        for c in collections:
            if c["id"] != coll["id"] and not is_excluded_folder(c.get("name")):
                others.update(c.get("post_ids") or [])
        members = coll.get("post_ids") or []
        to_hide = [sc for sc in members if sc not in others]
        kept = [sc for sc in members if sc in others]

        print(f"Collection '{coll['name'].strip()}' ({coll['id']}): {len(members)} post(s)")
        print(f"  hide (in no other collection): {len(to_hide)}  {' '.join(to_hide)}")
        print(f"  keep (also in another collection): {len(kept)}  {' '.join(kept)}")

        if args.apply:
            hidden = sum(1 for sc in to_hide if db.delete_post(sc))
            db.delete_collection(coll["id"])
            print(f"  -> hid {hidden} post(s), deleted collection row")

    if not args.apply:
        print("\nDry run — re-run with --apply to make these changes.")


if __name__ == "__main__":
    main()
