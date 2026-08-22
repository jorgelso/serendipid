#!/usr/bin/env python3
"""
Bulk-import an Instagram "Download Your Information" JSON export into a local
SuperBrain backend, preserving Instagram folder/collection structure as
SuperBrain collections.

Primary format: Meta's generic recursive "label_values" export shape
(confirmed against a real saved_collections.json export) — see
extract_meta_label_values_shape(). Two more permissive fallbacks exist for
older/other export variants: extract_known_shape() (the "string_map_data"/
"string_list_data" -> "href" shape some Instagram exports use) and a generic
recursive URL scan, so parsing degrades gracefully instead of hard-failing
on an unrecognized shape. If --dry-run counts look wrong, start by checking
which of these three actually matched your file.

Instagram's export always lists each collection newest-saved-first.
--reverse-collections (default: ON) reverses each collection's own slice of
records to oldest-first before they're processed, so posts get analyzed
(and stamped with analyzed_at) in the same order they were actually saved —
see reverse_within_collections() for the full reasoning. Only cross-category
order is left unfixed (there's no reliable signal in the export to unify
collections against each other); pass --no-reverse-collections only if you
specifically want the raw export order.

Usage:
    python import_saved_instagram.py <export.json-or-dir> --dry-run
    python import_saved_instagram.py <export.json-or-dir> --folder Recipes
    python import_saved_instagram.py <export.json-or-dir>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
import urllib.error
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

DEFAULT_SERVER_URL = "http://localhost:5050"
DEFAULT_STATE_FILE = SCRIPT_DIR / "import_state.json"
DEFAULT_DELAY_MIN = 8.0
DEFAULT_DELAY_MAX = 20.0
DEFAULT_MAX_ATTEMPTS = 5

# Same shortcode pattern as backend/core/link_checker.py::_validate_instagram
_IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────
# Export parsing
# ─────────────────────────────────────────────────────────────────────────

def shortcode_for(url: str) -> Optional[str]:
    m = _IG_URL_RE.search(url)
    return m.group(1) if m else None


def _iter_json_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
    else:
        yield from sorted(path.rglob("*.json"))


def _humanize_stem(stem: str) -> str:
    """Turn a filename stem like 'saved_recipes' into 'Saved Recipes'."""
    words = re.split(r"[_\-]+", stem)
    return " ".join(w.capitalize() for w in words if w)


def _extract_hrefs_from_item(item: Any) -> List[str]:
    """Pull href-like URLs out of a single saved-post entry, whatever shape
    it's in (string_map_data / string_list_data / plain href / plain url)."""
    urls: List[str] = []
    if isinstance(item, dict):
        smd = item.get("string_map_data")
        if isinstance(smd, dict):
            for v in smd.values():
                if isinstance(v, dict) and isinstance(v.get("href"), str):
                    urls.append(v["href"])
        sld = item.get("string_list_data")
        if isinstance(sld, list):
            for v in sld:
                if isinstance(v, dict) and isinstance(v.get("href"), str):
                    urls.append(v["href"])
        for key in ("href", "url"):
            if isinstance(item.get(key), str):
                urls.append(item[key])
    return urls


def _label_value(entry: Any, label: str) -> Optional[str]:
    """Get the 'value' (or 'href') of a {'label': ..., 'value': ...} entry."""
    if isinstance(entry, dict) and entry.get("label") == label:
        return entry.get("value") or entry.get("href")
    return None


def _extract_hashtag_names(hashtags_entry: Any) -> List[str]:
    """Pull hashtag names out of a {'dict': [{'dict': [{'label':'Name',...}], 'title':''}, ...], 'title':'Hashtags'} entry."""
    names: List[str] = []
    for sub in hashtags_entry.get("dict", []) if isinstance(hashtags_entry, dict) else []:
        if not isinstance(sub, dict):
            continue
        for inner in sub.get("dict", []):
            name = _label_value(inner, "Name")
            if name:
                names.append(name)
    return names


def extract_meta_label_values_shape(blob: Any) -> List[Tuple[str, str, str, List[str]]]:
    """
    Meta's generic recursive DYI export shape: a top-level list of collections,
    each with a 'label_values' list containing {'label','value'} metadata
    entries (Name, Type, Privacy, ...) plus one {'dict': [...], 'title': 'Media'}
    entry holding the actual saved posts. Each post is itself
    {'dict': [{'label': 'URL', ...}, {'label': 'Caption', ...},
    {'dict': [...], 'title': 'Hashtags'}, ...], 'title': ''}.
    Confirmed against a real "saved_collections.json" export. Returns []
    if the blob doesn't match this shape.

    Returns (folder, url, caption, hashtags) tuples.
    """
    if not isinstance(blob, list) or not blob:
        return []

    records: List[Tuple[str, str, str, List[str]]] = []
    matched_any_collection = False

    for item in blob:
        if not isinstance(item, dict) or not isinstance(item.get("label_values"), list):
            continue

        name = None
        posts_field = None
        for lv in item["label_values"]:
            if not isinstance(lv, dict):
                continue
            if lv.get("label") == "Name":
                name = lv.get("value")
            elif "dict" in lv:
                posts_field = lv

        if name is None or posts_field is None:
            continue
        matched_any_collection = True
        folder = (name or "").strip() or "Untitled"

        for post in posts_field.get("dict", []):
            if not isinstance(post, dict):
                continue
            url = None
            caption = ""
            hashtags: List[str] = []
            for field_entry in post.get("dict", []):
                if not isinstance(field_entry, dict):
                    continue
                if url is None:
                    u = _label_value(field_entry, "URL")
                    if u:
                        url = u
                        continue
                if not caption:
                    c = _label_value(field_entry, "Caption")
                    if c:
                        caption = c
                        continue
                if field_entry.get("title") == "Hashtags":
                    hashtags = _extract_hashtag_names(field_entry)
            if url:
                records.append((folder, url, caption, hashtags))

    return records if matched_any_collection else []


def _known_shape_items(blob: Any) -> Optional[Dict[str, List[Any]]]:
    """
    Try to recognize a top-level Instagram export shape and return
    {folder_name: [raw_item, ...]}. Returns None if nothing recognizable.
    """
    if isinstance(blob, dict):
        # Shape A: single well-known top-level list key (flat, no folder info)
        for key in ("saved_saved_media", "saved_media", "saved_posts", "ig_saved_media"):
            if isinstance(blob.get(key), list):
                return {"__flat__": blob[key]}

        # Shape B: dict keyed by collection name -> list of items
        list_valued = {
            k: v for k, v in blob.items()
            if isinstance(v, list) and v and all(isinstance(i, (dict, str)) for i in v)
        }
        if list_valued and not any(
            k in blob for k in ("string_map_data", "string_list_data", "href", "url")
        ):
            return list_valued

    if isinstance(blob, list):
        return {"__flat__": blob}

    return None


def extract_known_shape(blob: Any, fallback_folder: str) -> List[Tuple[str, str, str, List[str]]]:
    """Returns list of (folder, url, caption, hashtags) using the known-shape
    heuristics. This shape doesn't expose caption/hashtags, so those are empty."""
    grouped = _known_shape_items(blob)
    if grouped is None:
        return []

    records: List[Tuple[str, str, str, List[str]]] = []
    for folder_key, items in grouped.items():
        folder = fallback_folder if folder_key == "__flat__" else folder_key
        for item in items:
            for href in _extract_hrefs_from_item(item):
                records.append((folder, href, "", []))
    return records


def extract_fallback_urls(blob: Any, fallback_folder: str) -> List[Tuple[str, str, str, List[str]]]:
    """Generic recursive walk: collect every Instagram post/reel/tv URL found
    anywhere in the JSON tree, tagged with fallback_folder. Used only when
    extract_known_shape() finds nothing. No caption/hashtags in this mode."""
    found: List[str] = []

    def walk(node: Any):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            if _IG_URL_RE.search(node):
                found.append(node)

    walk(blob)
    return [(fallback_folder, u, "", []) for u in found]


def parse_export(path: Path) -> List[Tuple[str, str, str, List[str]]]:
    """Parse a single JSON file or a directory of JSON files into a flat
    list of (folder_name, instagram_url, caption, hashtags) records
    (duplicates allowed; caller dedupes by URL while preserving the set of
    folders each URL appeared in)."""
    all_records: List[Tuple[str, str, str, List[str]]] = []

    for json_file in _iter_json_files(path):
        try:
            blob = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Skipping unparseable file {json_file}: {e}")
            continue

        fallback_folder = _humanize_stem(json_file.stem)

        records = extract_meta_label_values_shape(blob)
        if not records:
            records = extract_known_shape(blob, fallback_folder)
        if not records:
            records = extract_fallback_urls(blob, fallback_folder)

        all_records.extend(records)

    # Keep only actual Instagram post/reel/tv URLs, normalize away tracking params
    cleaned: List[Tuple[str, str, str, List[str]]] = []
    for folder, url, caption, hashtags in all_records:
        code = shortcode_for(url)
        if not code:
            continue
        canonical = f"https://www.instagram.com/p/{code}/" if "/p/" in url \
            else f"https://www.instagram.com/reel/{code}/" if "/reel" in url \
            else url.split("?")[0]
        cleaned.append((folder, canonical, caption, hashtags))

    return cleaned


def reverse_within_collections(
    records: List[Tuple[str, str, str, List[str]]]
) -> List[Tuple[str, str, str, List[str]]]:
    """Group (folder, url, caption, hashtags) records by folder, preserving
    first-seen folder order, and reverse each folder's internal item order.

    Instagram's "Download Your Information" export always lists a saved
    collection newest-saved-first. Feeding that order straight into
    analyze_url() would stamp newer reels with an OLDER analyzed_at than
    reels that get processed later in the same run — inverting the real
    chronology. Reversing each collection's slice to oldest-first before
    processing means analyzed_at increases in the same order the posts were
    actually saved. Cross-category order is deliberately left as-is (the
    export gives no reliable signal to unify collections against each
    other) — only a single collection's own internal order is corrected.
    """
    by_folder: "OrderedDict[str, List[Tuple[str, str, str, List[str]]]]" = OrderedDict()
    for rec in records:
        by_folder.setdefault(rec[0], []).append(rec)
    out: List[Tuple[str, str, str, List[str]]] = []
    for _folder, recs in by_folder.items():
        out.extend(reversed(recs))
    return out


def group_by_url(records: List[Tuple[str, str, str, List[str]]]) -> Dict[str, List[str]]:
    """(folder, url, caption, hashtags) records -> {url: [folder, ...]}
    preserving first-seen order, deduped per URL (a post saved in the same
    folder twice only counts once)."""
    result: Dict[str, List[str]] = {}
    for folder, url, _caption, _hashtags in records:
        folders = result.setdefault(url, [])
        if folder not in folders:
            folders.append(folder)
    return result


def build_url_metadata(records: List[Tuple[str, str, str, List[str]]]) -> Dict[str, Tuple[str, List[str]]]:
    """(folder, url, caption, hashtags) records -> {url: (caption, hashtags)},
    first non-empty caption/hashtags seen for a URL wins (a post saved into
    multiple collections should have the same caption/hashtags anyway)."""
    result: Dict[str, Tuple[str, List[str]]] = {}
    for _folder, url, caption, hashtags in records:
        existing_caption, existing_hashtags = result.get(url, ("", []))
        result[url] = (existing_caption or caption, existing_hashtags or hashtags)
    return result


# ─────────────────────────────────────────────────────────────────────────
# State file
# ─────────────────────────────────────────────────────────────────────────

def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not read state file {state_file} ({e}); starting fresh.")
    return {"posts": {}, "collections": {}}


def save_state(state_file: Path, state: dict) -> None:
    tmp = state_file.with_suffix(state_file.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, state_file)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────
# HTTP client (stdlib only — no extra dependency beyond what's already
# in backend/requirements.txt for the server itself; this script runs
# standalone so we avoid requiring `requests` to be on PATH)
# ─────────────────────────────────────────────────────────────────────────

class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def api_request(
    method: str, base_url: str, path: str, api_key: str,
    json_body: Optional[dict] = None, timeout: float = 600.0,
) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", api_key)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        detail = body
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            pass
        raise ApiError(e.code, str(detail)) from None
    except urllib.error.URLError as e:
        raise ApiError(0, f"Connection error: {e.reason}") from None


# ─────────────────────────────────────────────────────────────────────────
# Collections
# ─────────────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "untitled"


@dataclass
class CollectionState:
    id: str
    exists_on_server: bool
    post_ids: Set[str] = field(default_factory=set)


def load_collections(base_url: str, api_key: str) -> Dict[str, CollectionState]:
    """Seed in-memory collection state from what's already on the server,
    keyed by our deterministic id (ig_<slug>) so we never clobber posts
    a collection already has."""
    by_id: Dict[str, CollectionState] = {}
    try:
        resp = api_request("GET", base_url, "/collections", api_key)
        for c in resp.get("data", []):
            by_id[c["id"]] = CollectionState(
                id=c["id"], exists_on_server=True,
                post_ids=set(c.get("post_ids") or []),
            )
    except ApiError as e:
        print(f"[WARN] Could not fetch existing collections ({e}); assuming none exist yet.")
    return by_id


def ensure_post_in_collection(
    base_url: str, api_key: str, folder_name: str,
    shortcode: str, collections_by_id: Dict[str, CollectionState],
) -> str:
    """Make sure `shortcode` is in the collection matching folder_name,
    creating the collection if needed. Returns the collection id used."""
    coll_id = "ig_" + slugify(folder_name)
    state = collections_by_id.get(coll_id)

    if state is None:
        state = CollectionState(id=coll_id, exists_on_server=False, post_ids=set())
        collections_by_id[coll_id] = state

    if shortcode in state.post_ids:
        return coll_id  # already assigned, nothing to do

    state.post_ids.add(shortcode)
    post_ids_list = sorted(state.post_ids)

    if not state.exists_on_server:
        api_request("POST", base_url, "/collections", api_key, {
            "id": coll_id,
            "name": folder_name,
            "icon": "📁",
            "post_ids": post_ids_list,
        })
        state.exists_on_server = True
    else:
        api_request("PUT", base_url, f"/collections/{coll_id}/posts", api_key, {
            "post_ids": post_ids_list,
        })

    return coll_id


# ─────────────────────────────────────────────────────────────────────────
# Analyze
# ─────────────────────────────────────────────────────────────────────────

def analyze_url(
    base_url: str, api_key: str, url: str, force: bool,
    caption: str = "", hashtags: Optional[List[str]] = None,
) -> dict:
    body: Dict[str, Any] = {"url": url, "force": force}
    if caption:
        body["caption"] = caption
    if hashtags:
        body["hashtags"] = hashtags
    return api_request("POST", base_url, "/analyze", api_key, body)


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def resolve_api_key(cli_value: Optional[str]) -> str:
    if cli_value:
        return cli_value
    env_value = os.environ.get("SUPERBRAIN_API_KEY")
    if env_value:
        return env_value
    token_file = BACKEND_DIR / "token.txt"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    print(
        "[ERROR] No API key found. Pass --api-key, set SUPERBRAIN_API_KEY, "
        f"or make sure {token_file} exists (created automatically the first "
        "time the backend server starts)."
    )
    sys.exit(1)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("export_path", type=Path, help="Path to the Instagram export JSON file, or a directory of them")
    p.add_argument("--folder", help="Only process URLs from this Instagram folder/collection (case-insensitive)")
    p.add_argument(
        "--reverse-collections", dest="reverse_collections",
        action="store_true", default=True,
        help="Process each collection oldest-saved-first (default: on). Instagram's "
             "export lists newest-saved-first; leaving this on keeps analyzed_at "
             "chronologically meaningful. Only disable if you specifically want the "
             "raw export order.",
    )
    p.add_argument(
        "--no-reverse-collections", dest="reverse_collections", action="store_false",
        help="Process collections in the raw export order (newest-saved-first).",
    )
    p.add_argument("--server-url", default=DEFAULT_SERVER_URL, help=f"SuperBrain backend URL (default: {DEFAULT_SERVER_URL})")
    p.add_argument("--api-key", help="X-API-Key value (default: backend/token.txt, then $SUPERBRAIN_API_KEY)")
    p.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE, help=f"Resumable state file (default: {DEFAULT_STATE_FILE})")
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

    url_to_folders = group_by_url(records)
    url_meta = build_url_metadata(records)

    folder_counts: Dict[str, int] = {}
    for folders in url_to_folders.values():
        for f in folders:
            folder_counts[f] = folder_counts.get(f, 0) + 1

    print(f"Parsed {len(url_to_folders)} unique Instagram URL(s) across {len(folder_counts)} folder(s):")
    for folder, count in sorted(folder_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {folder:<30} {count}")

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
            try:
                analyze_url(args.server_url, api_key, url, args.force, caption, hashtags)
                entry["status"] = "success"
                entry["last_error"] = None
                success_count += 1
                print(f"[{i}/{total}]   OK")
            except ApiError as e:
                entry["attempts"] += 1
                entry["last_error"] = f"{e.status}: {e.detail}"
                if e.status == 202:
                    print(f"[{i}/{total}]   RATE-LIMITED / quota exhausted, server will retry in 24h: {e.detail}")
                elif e.status == 503:
                    print(f"[{i}/{total}]   SERVER BUSY, queued server-side: {e.detail}")
                elif e.status == 409:
                    print(f"[{i}/{total}]   ALREADY PROCESSING: {e.detail}")
                elif e.status == 504:
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

    # Per-collection breakdown — a post saved in 2+ collections appears
    # under each of its folders here, matching how it's assigned server-side.
    per_folder: Dict[str, Dict[str, int]] = {}
    for entry in posts_state.values():
        for folder in entry.get("folders", []):
            counts = per_folder.setdefault(folder, {"success": 0, "pending": 0, "permanently_skipped": 0})
            status = entry.get("status", "pending")
            if status not in counts:
                status = "pending"
            counts[status] += 1

    if per_folder:
        print("\nBy collection:")
        for folder, counts in sorted(per_folder.items(), key=lambda kv: -sum(kv[1].values())):
            total_f = sum(counts.values())
            print(
                f"  {folder:<30} {total_f:>5} total   "
                f"success={counts['success']}  pending={counts['pending']}  skipped={counts['permanently_skipped']}"
            )


if __name__ == "__main__":
    main()
