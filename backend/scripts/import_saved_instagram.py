#!/usr/bin/env python3
"""
Bulk-import an Instagram "Download Your Information" JSON export into a local
Serendipid backend, preserving Instagram folder/collection structure as
Serendipid collections.

Primary format: Meta's generic recursive "label_values" export shape
(confirmed against a real saved_collections.json export) — see
extract_meta_label_values_shape(). Two more permissive fallbacks exist for
older/other export variants: extract_known_shape() (the "string_map_data"/
"string_list_data" -> "href" shape some Instagram exports use) and a generic
recursive URL scan, so parsing degrades gracefully instead of hard-failing
on an unrecognized shape. If --dry-run counts look wrong, start by checking
which of these three actually matched your file.

Two input files, two different jobs:
  - <export.json-or-dir> (positional, required): the "by collection" export
    (saved_collections.json-shaped) — decides WHAT gets analyzed and which
    Serendipid collection(s) it's assigned to. Only posts saved in a
    collection are ever analyzed by this script.
  - --all-posts-file (optional): a flat "every saved post, ungrouped" export
    (saved_posts.json-shaped) — used ONLY to look up each analyzed post's
    real save date (analyses.date_saved), via each entry's own `timestamp`
    field. Verified to be a save date, not a publish date (see the
    date_saved migration comment in core/database.py). A post in this file
    that isn't also in the collections file is never analyzed on its own —
    it's a lookup table, not a second source of URLs.

Instagram's collection export always lists each collection newest-saved-
first. --reverse-collections (default: OFF) reverses each collection's own
slice of records to oldest-first before they're processed, purely as a
processing-order preference — analyzed_at no longer needs to reflect save
order for date accuracy now that real dates come from --all-posts-file, so
the default is off, meaning the newest-saved reels in each collection get
analyzed (and become searchable) first. See reverse_within_collections() for
the full reasoning; only cross-category order is left unfixed regardless.

Usage:
    python import_saved_instagram.py <export.json-or-dir> --dry-run
    python import_saved_instagram.py <export.json-or-dir> --all-posts-file saved_posts.json
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

sys.path.insert(0, str(BACKEND_DIR))
from core.sensitive import is_excluded_folder  # noqa: E402

DEFAULT_SERVER_URL = "http://localhost:5050"
DEFAULT_STATE_FILE = SCRIPT_DIR / "import_state.json"
DEFAULT_DELAY_MIN = 8.0
DEFAULT_DELAY_MAX = 20.0
DEFAULT_MAX_ATTEMPTS = 5

# /analyze responses that mean "the backend owns this now and will finish it
# itself", as opposed to "this attempt failed". These must never count against
# --max-attempts — see the handler in run_import() for the full reasoning.
# Shared with import_saved_instagram_by_collection.py, which imports it.
#
#   202  queued a 24h automatic retry, or submitted to the OpenAI Batch API
#   503  backend busy — the request went into processing_queue
#   409  already in flight: currently being analyzed, or (since the
#        status='batch' admission guard) already submitted to a batch
HANDED_OFF_TO_SERVER = frozenset({202, 409, 503})

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


def looks_like_collections_export(blob: Any) -> bool:
    """Cheap structural check, no full parse: does blob look like a
    saved_collections.json-shaped export (top-level list, at least one item
    with a label_values list containing both a Name label and a Media-like
    dict entry)? Mirrors extract_meta_label_values_shape()'s own matching
    condition exactly, so "this parses" and "this validates" never disagree.
    Used by api.py's /instagram-export/* routes to reject a JSON upload
    that isn't actually this shape, before it's ever written to disk or
    handed to a subprocess.
    """
    if not isinstance(blob, list) or not blob:
        return False
    for item in blob:
        if not isinstance(item, dict) or not isinstance(item.get("label_values"), list):
            continue
        has_name = any(isinstance(lv, dict) and lv.get("label") == "Name" for lv in item["label_values"])
        has_media = any(isinstance(lv, dict) and "dict" in lv for lv in item["label_values"])
        if has_name and has_media:
            return True
    return False


def looks_like_all_posts_export(blob: Any) -> bool:
    """Cheap structural check, no full parse: does blob look like a
    saved_posts.json-shaped export (top-level list, at least one item with
    its own numeric top-level `timestamp` and a label_values list
    containing a URL directly, not nested inside a Media dict)? Mirrors
    extract_post_timestamps()'s own matching condition. The Name-vs-URL
    distinction is what tells this apart from looks_like_collections_export
    above — both shapes' top-level items can carry a `timestamp` field
    (a collections file's is a collection-level timestamp), so `timestamp`
    alone isn't a reliable signal on its own.
    """
    if not isinstance(blob, list) or not blob:
        return False
    for item in blob:
        if not isinstance(item, dict) or not isinstance(item.get("label_values"), list):
            continue
        if not isinstance(item.get("timestamp"), (int, float)):
            continue
        if any(isinstance(lv, dict) and lv.get("label") == "URL" for lv in item["label_values"]):
            return True
    return False


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

    # Keep only actual Instagram post/reel/tv URLs, normalize away tracking params.
    # Records from an excluded folder (core/sensitive.py) are dropped here, so
    # a post saved only there is never imported, and one also saved elsewhere
    # is imported without ever being assigned to it.
    cleaned: List[Tuple[str, str, str, List[str]]] = []
    for folder, url, caption, hashtags in all_records:
        if is_excluded_folder(folder):
            continue
        code = shortcode_for(url)
        if not code:
            continue
        canonical = f"https://www.instagram.com/p/{code}/" if "/p/" in url \
            else f"https://www.instagram.com/reel/{code}/" if "/reel" in url \
            else url.split("?")[0]
        cleaned.append((folder, canonical, caption, hashtags))

    return cleaned


def extract_post_timestamps(path: Path) -> Dict[str, str]:
    """Parse a flat "every saved post, ungrouped" export (saved_posts.json-
    shaped — a top-level list where each entry has its own `label_values`
    directly, no collection `Name`/`Media` wrapper, plus a sibling
    `timestamp` field) into {shortcode: iso_date_string}.

    This is a genuinely different shape from the collections export's
    (extract_meta_label_values_shape() requires a `Name` label per
    top-level item, which entries here don't have, so it returns [] for
    this file). `timestamp` here is the real date the post was SAVED to
    Instagram, not its publish date — verified against analyses.post_date
    (see the date_saved migration comment in core/database.py): it's always
    later than post_date, by a wildly varying amount, the signature of
    "whenever I happened to see and save this," not a duplicate publish
    date. Entries with no parseable URL or timestamp are skipped silently.
    """
    result: Dict[str, str] = {}
    for json_file in _iter_json_files(path):
        try:
            blob = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Skipping unparseable file {json_file}: {e}")
            continue
        if not isinstance(blob, list):
            continue
        for entry in blob:
            if not isinstance(entry, dict):
                continue
            label_values = entry.get("label_values")
            ts = entry.get("timestamp")
            if not isinstance(label_values, list) or not isinstance(ts, (int, float)):
                continue
            url = None
            for lv in label_values:
                u = _label_value(lv, "URL")
                if u:
                    url = u
                    break
            code = shortcode_for(url) if url else None
            if code:
                result[code] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return result


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
            parsed = json.loads(body) if body else {}
            # urlopen() only raises HTTPError for 4xx/5xx — a 2xx status
            # other than 200 (in practice, /analyze's 202 "queued for
            # retry server-side, nothing saved yet" response) reaches here
            # as if it were a normal success. Left unchecked, main()'s loop
            # would mark the item "success" even though nothing was
            # actually analyzed — confirmed in practice: 39 posts queued
            # server-side for a Whisper-failure retry were silently marked
            # done locally and never revisited. Raising ApiError here
            # routes a non-200 status through the *already-existing*
            # e.status == 202 handling in main()'s except block below,
            # which was clearly written assuming this would happen but
            # never actually fired.
            if resp.status != 200:
                detail = parsed.get("detail", body) if isinstance(parsed, dict) else body
                raise ApiError(resp.status, str(detail))
            return parsed
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
    except OSError as e:
        # A request that hangs past `timeout` (e.g. main.py stuck on an
        # unusually slow download/analysis) can raise a bare TimeoutError
        # (or another raw socket-level OSError) straight out of urlopen()
        # without it ever becoming a urllib.error.URLError — seen in
        # practice: a TimeoutError surfacing mid-response-read after the
        # full 600s timeout elapsed, which the two except clauses above
        # don't catch, crashing the whole script instead of just failing
        # this one URL. Wrapping it as an ApiError routes it through the
        # exact same per-URL retry/skip handling in main()'s loop as any
        # other failure, so one slow item can't take down an entire run.
        raise ApiError(0, f"{type(e).__name__}: {e}") from None


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
    date_saved: Optional[str] = None,
) -> dict:
    body: Dict[str, Any] = {"url": url, "force": force}
    if caption:
        body["caption"] = caption
    if hashtags:
        body["hashtags"] = hashtags
    if date_saved:
        body["date_saved"] = date_saved
    return api_request("POST", base_url, "/analyze", api_key, body)


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def resolve_api_key(cli_value: Optional[str]) -> str:
    if cli_value:
        return cli_value
    env_value = os.environ.get("SERENDIPID_API_KEY")
    if env_value:
        return env_value
    token_file = BACKEND_DIR / "token.txt"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    print(
        "[ERROR] No API key found. Pass --api-key, set SERENDIPID_API_KEY, "
        f"or make sure {token_file} exists (created automatically the first "
        "time the backend server starts)."
    )
    sys.exit(1)


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
    p.add_argument("--server-url", default=DEFAULT_SERVER_URL, help=f"Serendipid backend URL (default: {DEFAULT_SERVER_URL})")
    p.add_argument("--api-key", help="X-API-Key value (default: backend/token.txt, then $SERENDIPID_API_KEY)")
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
            # State written before EXCLUDED_IMPORT_FOLDERS existed may still
            # list one — never assign the post to it.
            entry["folders"] = [f for f in entry["folders"] if not is_excluded_folder(f)]

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
                    # The backend took ownership of this URL and will finish
                    # it on its own schedule — 202 means it queued a later
                    # automatic retry (Whisper/transcription failed
                    # server-side, an AI quota is exhausted) or submitted the
                    # analysis to the OpenAI Batch API; 503 means it was busy
                    # and put the request in processing_queue for
                    # queue_worker() to pick up; 409 means it's already in
                    # flight, either being analyzed right now or sitting in a
                    # batch. None is a failure caused by this script, and
                    # none is saved yet.
                    #
                    # Deliberately doesn't count against max_attempts: the
                    # backend keeps working on it regardless of how many times
                    # this script happens to run in the meantime, so letting
                    # these burn attempts would mark a perfectly good reel
                    # permanently_skipped for nothing. Always stays "pending"
                    # so a later run re-checks it — harmless either way: an
                    # instant cache hit if the backend already finished it, or
                    # it simply gets queued again.
                    if e.status == 503:
                        print(f"[{i}/{total}]   SERVER BUSY, queued server-side (will be analyzed automatically): {e.detail}")
                    elif e.status == 409:
                        print(f"[{i}/{total}]   ALREADY IN FLIGHT server-side: {e.detail}")
                    else:
                        print(f"[{i}/{total}]   QUEUED server-side (not yet saved), will retry automatically: {e.detail}")
                    entry["status"] = "pending"
                    pending_count += 1
                else:
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
            # /analyze already returned instantly, no real work (download/AI
            # calls) happened, so there's nothing to throttle. A failed
            # attempt (ApiError, cached=False left as its default) still
            # sleeps as before.
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
