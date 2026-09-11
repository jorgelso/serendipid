#!/usr/bin/env python3
"""
Bulk-import an Instagram "Download Your Information" JSON export into a local
SuperBrain backend, same as import_saved_instagram.py, but processes reels in
collection-priority order: everything in the --priority-folder collection
(default "Important") is analyzed first, then every other collection in its
original relative order from the export file.

Reuses all parsing/state/API/collection-assignment logic from
import_saved_instagram.py (must be run from this directory, or via its
absolute path, so that sibling-module import works) and shares the same
resumable state file by default, so runs of either script are safe to
interleave — a URL already marked "success" is skipped regardless of which
script processed it.

Also reuses import_saved_instagram.py's --reverse-collections (default: OFF)
and --all-posts-file (real save-date lookup, see that script's docstring for
the full two-file explanation) — reversal is applied before the priority
reorder below, since the two are independent: reversal fixes each
collection's own internal order, priority-reordering only decides which
collection is scheduled first.

Usage:
    python import_saved_instagram_by_collection.py <export.json-or-dir> --dry-run
    python import_saved_instagram_by_collection.py <export.json-or-dir> --priority-folder Important
    python import_saved_instagram_by_collection.py <export.json-or-dir>
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

from import_saved_instagram import (
    ApiError,
    CollectionState,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_SERVER_URL,
    DEFAULT_STATE_FILE,
    HANDED_OFF_TO_SERVER,
    analyze_url,
    build_url_metadata,
    ensure_post_in_collection,
    extract_post_timestamps,
    group_by_url,
    load_collections,
    load_state,
    now_iso,
    parse_export,
    resolve_api_key,
    reverse_within_collections,
    save_state,
    shortcode_for,
)

DEFAULT_PRIORITY_FOLDER = "Important"


def reorder_by_collection_priority(
    records: List[Tuple[str, str, str, List[str]]],
    priority_folder: str = DEFAULT_PRIORITY_FOLDER,
) -> List[Tuple[str, str, str, List[str]]]:
    """Stable-partition (folder, url, caption, hashtags) records so every
    record whose folder case-insensitively matches priority_folder (after
    stripping whitespace) comes first, in original relative order, followed
    by every other record, also in original relative order. Internal order
    within each collection is untouched.

    Feeding the result into group_by_url() unmodified naturally yields
    first-seen url ordering with priority_folder's URLs first, even for a
    URL that also belongs to another (later) collection.
    """
    priority_key = priority_folder.strip().lower()
    priority_records = [r for r in records if r[0].strip().lower() == priority_key]
    other_records = [r for r in records if r[0].strip().lower() != priority_key]
    if not priority_records:
        print(
            f"[WARN] No records found for priority folder '{priority_folder}'; "
            f"falling back to original collection order."
        )
    return priority_records + other_records


def _ordered_folder_names(
    records: List[Tuple[str, str, str, List[str]]]
) -> List[str]:
    """First-seen folder names in `records`, i.e. the processing order."""
    ordered: List[str] = []
    seen = set()
    for folder, _url, _caption, _hashtags in records:
        if folder not in seen:
            seen.add(folder)
            ordered.append(folder)
    return ordered


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("export_path", type=Path, help="Path to the Instagram \"by collection\" export JSON file, or a directory of them")
    p.add_argument(
        "--all-posts-file", type=Path, default=None,
        help="Path to a flat 'saved_posts.json'-style export (every individually-saved "
             "post, ungrouped) — used only to look up each analyzed post's real save "
             "date. Posts here that aren't also in the collections file are never "
             "analyzed on their own. Optional; omit to skip date_saved for this run.",
    )
    p.add_argument("--folder", help="Only process URLs from this Instagram folder/collection (case-insensitive)")
    p.add_argument(
        "--priority-folder",
        default=DEFAULT_PRIORITY_FOLDER,
        help=f"Collection to schedule first, case-insensitive (default: {DEFAULT_PRIORITY_FOLDER})",
    )
    p.add_argument(
        "--reverse-collections", dest="reverse_collections",
        action="store_true", default=False,
        help="Process each collection oldest-saved-first (default: off). Purely a "
             "processing-order preference now — real save dates come from "
             "--all-posts-file regardless of analysis order. Off by default means the "
             "newest-saved reels in each collection get analyzed (and become "
             "searchable) first.",
    )
    p.add_argument(
        "--no-reverse-collections", dest="reverse_collections", action="store_false",
        help="Process collections in the raw export order, newest-saved-first (the default).",
    )
    p.add_argument("--server-url", default=DEFAULT_SERVER_URL, help=f"SuperBrain backend URL (default: {DEFAULT_SERVER_URL})")
    p.add_argument("--api-key", help="X-API-Key value (default: backend/token.txt, then $SUPERBRAIN_API_KEY)")
    p.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE, help=f"Resumable state file, shared with import_saved_instagram.py (default: {DEFAULT_STATE_FILE})")
    p.add_argument("--delay-min", type=float, default=DEFAULT_DELAY_MIN, help=f"Minimum delay between /analyze calls, seconds (default: {DEFAULT_DELAY_MIN})")
    p.add_argument("--delay-max", type=float, default=DEFAULT_DELAY_MAX, help=f"Maximum delay between /analyze calls, seconds (default: {DEFAULT_DELAY_MAX})")
    p.add_argument("--force", action="store_true", help="Pass force=true to /analyze (bypass cache, re-download)")
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help=f"Give up on a URL after this many failed attempts (default: {DEFAULT_MAX_ATTEMPTS})")
    p.add_argument("--limit", type=int, default=None, help="Stop after this many URLs are actually submitted (for a small test run)")
    p.add_argument("--dry-run", action="store_true", help="Parse and print per-folder counts only; no network calls, no state writes")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    if not args.export_path.exists():
        print(f"[ERROR] Path not found: {args.export_path}")
        sys.exit(1)

    records = parse_export(args.export_path)
    if args.folder:
        records = [r for r in records if r[0].lower() == args.folder.lower()]
    if args.reverse_collections:
        records = reverse_within_collections(records)

    records = reorder_by_collection_priority(records, priority_folder=args.priority_folder)

    url_to_folders = group_by_url(records)
    url_meta = build_url_metadata(records)

    post_timestamps: Dict[str, str] = {}
    if args.all_posts_file:
        if not args.all_posts_file.exists():
            print(f"[ERROR] --all-posts-file not found: {args.all_posts_file}")
            sys.exit(1)
        post_timestamps = extract_post_timestamps(args.all_posts_file)
        print(f"Loaded {len(post_timestamps)} save-date(s) from {args.all_posts_file}.")

    folder_counts: Dict[str, int] = {}
    for folders in url_to_folders.values():
        for f in folders:
            folder_counts[f] = folder_counts.get(f, 0) + 1

    priority_key = args.priority_folder.strip().lower()
    print(f"Parsed {len(url_to_folders)} unique Instagram URL(s) across {len(folder_counts)} folder(s), in priority order:")
    for folder in _ordered_folder_names(records):
        marker = "  <- priority" if folder.strip().lower() == priority_key else ""
        print(f"  {folder:<30} {folder_counts.get(folder, 0)}{marker}")

    if args.dry_run:
        print("\n[dry-run] No requests sent, no state file written.")
        return

    if not url_to_folders:
        print("Nothing to do.")
        return

    api_key = resolve_api_key(args.api_key)
    state = load_state(args.state_file)
    posts_state: dict = state.setdefault("posts", {})
    collections_state: dict = state.setdefault("collections", {})
    collections_by_id = load_collections(args.server_url, api_key)
    # Restore any collection ids we created in a previous run that the
    # server-side GET didn't happen to include (defensive; normally redundant).
    for folder, coll_id in collections_state.items():
        collections_by_id.setdefault(coll_id, CollectionState(id=coll_id, exists_on_server=True))

    submitted = 0
    total = len(url_to_folders)
    success_count = pending_count = skipped_count = 0

    for i, (url, folders) in enumerate(url_to_folders.items(), start=1):
        entry = posts_state.get(url)
        if entry is None:
            entry = {
                "shortcode": shortcode_for(url),
                "status": "pending",
                "attempts": 0,
                "last_error": None,
                "last_updated": now_iso(),
                "folders": folders,
                "assigned_folders": [],
            }
            posts_state[url] = entry
        else:
            for f in folders:
                if f not in entry["folders"]:
                    entry["folders"].append(f)

        shortcode = entry["shortcode"]
        if not shortcode:
            print(f"[{i}/{total}] SKIP (no shortcode parsed) {url}")
            continue

        if entry["status"] == "success":
            success_count += 1
        elif entry["status"] == "permanently_skipped":
            skipped_count += 1
        else:
            if args.limit is not None and submitted >= args.limit:
                pending_count += 1
                continue

            print(f"[{i}/{total}] Analyzing {shortcode} ({', '.join(folders)}) ...")
            submitted += 1
            caption, hashtags = url_meta.get(url, ("", []))
            date_saved = post_timestamps.get(shortcode)
            cached = False
            try:
                result = analyze_url(args.server_url, api_key, url, args.force, caption, hashtags, date_saved)
                cached = bool(result.get("cached"))
                entry["status"] = "success"
                entry["last_error"] = None
                success_count += 1
                print(f"[{i}/{total}]   OK" + (" (cached)" if cached else ""))
            except ApiError as e:
                entry["last_error"] = f"{e.status}: {e.detail}"
                if e.status in HANDED_OFF_TO_SERVER:
                    # Backend owns this now and will finish it on its own — a
                    # 24h retry or a Batch API submission (202), a
                    # processing_queue slot (503), or an analysis already in
                    # flight (409). Not a failed attempt, so it must not count
                    # against --max-attempts; see the matching handler in
                    # import_saved_instagram.py for the full reasoning.
                    if e.status == 503:
                        print(f"[{i}/{total}]   SERVER BUSY, queued server-side (will be analyzed automatically): {e.detail}")
                    elif e.status == 409:
                        print(f"[{i}/{total}]   ALREADY IN FLIGHT server-side: {e.detail}")
                    else:
                        print(f"[{i}/{total}]   RATE-LIMITED / quota exhausted, server will retry in 24h: {e.detail}")
                    entry["status"] = "pending"
                    pending_count += 1
                    entry["last_updated"] = now_iso()
                    save_state(args.state_file, state)
                    time.sleep(random.uniform(args.delay_min, args.delay_max))
                    continue

                entry["attempts"] += 1
                if e.status == 504:
                    print(f"[{i}/{total}]   TIMEOUT (10 min): {e.detail}")
                elif e.status == 410:
                    # User deleted this post via a client — respect that and
                    # stop retrying rather than re-submitting every run.
                    print(f"[{i}/{total}]   DELETED by user, skipping: {e.detail}")
                else:
                    print(f"[{i}/{total}]   FAILED ({e.status}): {e.detail}")

                if e.status == 410 or entry["attempts"] >= args.max_attempts:
                    entry["status"] = "permanently_skipped"
                    skipped_count += 1
                    if e.status != 410:
                        print(f"[{i}/{total}]   Giving up after {entry['attempts']} attempts.")
                else:
                    entry["status"] = "pending"
                    pending_count += 1

            entry["last_updated"] = now_iso()
            save_state(args.state_file, state)

            # Skip the artificial rate-limit delay on a confirmed cache hit —
            # see the matching comment in import_saved_instagram.py.
            if not cached:
                time.sleep(random.uniform(args.delay_min, args.delay_max))

        # Collection assignment (runs for newly-succeeded AND previously-succeeded
        # entries, so a crash between "analyzed" and "assigned" is resumed correctly)
        if entry["status"] == "success":
            changed = False
            for folder in entry["folders"]:
                if folder in entry["assigned_folders"]:
                    continue
                try:
                    coll_id = ensure_post_in_collection(
                        args.server_url, api_key, folder, shortcode, collections_by_id
                    )
                    collections_state[folder] = coll_id
                    entry["assigned_folders"].append(folder)
                    changed = True
                except ApiError as e:
                    print(f"[{i}/{total}]   WARN: could not assign to collection '{folder}': {e}")
            if changed:
                entry["last_updated"] = now_iso()
                save_state(args.state_file, state)

    save_state(args.state_file, state)

    print("\nDone.")
    print(f"  success:             {success_count}")
    print(f"  pending (will retry on next run): {pending_count}")
    print(f"  permanently_skipped: {skipped_count}")
    print(f"State file: {args.state_file}")

    # Per-collection breakdown, in priority order — a post saved in 2+
    # collections appears under each of its folders here, matching how it's
    # assigned server-side.
    per_folder: Dict[str, Dict[str, int]] = {}
    for entry in posts_state.values():
        for folder in entry.get("folders", []):
            counts = per_folder.setdefault(folder, {"success": 0, "pending": 0, "permanently_skipped": 0})
            status = entry.get("status", "pending")
            if status not in counts:
                status = "pending"
            counts[status] += 1

    if per_folder:
        print("\nBy collection (priority order):")
        for folder in _ordered_folder_names(records):
            if folder not in per_folder:
                continue
            counts = per_folder[folder]
            total_f = sum(counts.values())
            marker = "  <- priority" if folder.strip().lower() == priority_key else ""
            print(
                f"  {folder:<30} {total_f:>5} total   "
                f"success={counts['success']}  pending={counts['pending']}  skipped={counts['permanently_skipped']}{marker}"
            )


if __name__ == "__main__":
    main()
