#!/usr/bin/env python3
"""
One-time backfill: re-encode every video under media/<shortcode>/ to a smaller
H.264 file, replacing the original in place.

Instagram serves reels at a fairly generous bitrate (~1.2 Mbps median here,
2-5 Mbps at the top end) and the mp4s are ~90% of media/ on disk. Re-encoding
with libx264 at a higher CRF gets ~40% back at near-transparent quality for a
phone-sized reference library. Only the video stream is touched — audio is
stream-copied (it's already tiny HE-AAC), and the filename never changes, so
`analyses.media_files` and every /media/<shortcode>/<file> URL stay valid.
Rescans keep working too: analyzers/visual_analyze.py only samples frames.

Safety:
  - Encodes to a temp file next to the original and only os.replace()s it in
    once ffmpeg succeeded, the output is actually smaller, and its duration
    matches the source. A failed or useless encode leaves the original alone.
  - Every file that's been through here gets a `comment` metadata tag, so
    re-running the script skips it (resumable after Ctrl-C / crash, and never
    stacks a second generation of loss on top of the first). Files that were
    already too small to benefit get the tag via a cheap `-c copy` remux.
  - Originals are NOT kept. Back media/ up first if you want them.

Usage:
    cd backend
    .venv/bin/python scripts/reencode_media.py [--crf 30] [--workers 4]
                                               [--limit N] [--dry-run]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.media_store import MEDIA_DIR

TAG_KEY = "comment"
TAG_PREFIX = "superbrain-reencoded"

# Don't bother replacing the original unless we actually save something —
# a re-encode that lands within a few percent isn't worth the quality cost.
MIN_SAVINGS_RATIO = 0.90
# Output must be within this many seconds of the source duration, otherwise
# something went wrong (truncated encode, bad container) and we keep the source.
MAX_DURATION_DRIFT_S = 1.0


def probe(path: Path) -> dict:
    """Return {codec, duration, tag} for the file (any field may be None)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", f"stream=codec_name:format=duration:format_tags={TAG_KEY}",
        "-of", "json", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return {"codec": None, "duration": None, "tag": None}
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams") or [{}]
    fmt = data.get("format") or {}
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        duration = None
    return {
        "codec": streams[0].get("codec_name"),
        "duration": duration,
        "tag": (fmt.get("tags") or {}).get(TAG_KEY),
    }


def already_done(info: dict) -> bool:
    return bool(info["tag"] and str(info["tag"]).startswith(TAG_PREFIX))


def encode(src: Path, crf: int) -> tuple:
    """Re-encode *src* in place. Returns (status, in_bytes, out_bytes, detail)."""
    info = probe(src)
    in_bytes = src.stat().st_size
    if already_done(info):
        return ("skipped", in_bytes, in_bytes, "already re-encoded")
    if info["codec"] is None:
        return ("failed", in_bytes, in_bytes, "ffprobe could not read file")

    tag = f"{TAG_PREFIX}:x264-crf{crf}"
    tmp = src.with_name(f".{src.name}.reencode.tmp.mp4")
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-y",
        "-i", str(src),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-map_metadata", "-1",
        "-metadata", f"{TAG_KEY}={tag}",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not tmp.exists():
            return ("failed", in_bytes, in_bytes, (res.stderr or "ffmpeg failed").strip()[-300:])

        out_bytes = tmp.stat().st_size
        out_info = probe(tmp)
        if (
            info["duration"] is not None
            and out_info["duration"] is not None
            and abs(info["duration"] - out_info["duration"]) > MAX_DURATION_DRIFT_S
        ):
            return ("failed", in_bytes, in_bytes,
                    f"duration drift {info['duration']:.1f}s -> {out_info['duration']:.1f}s")

        if out_bytes < in_bytes * MIN_SAVINGS_RATIO:
            os.replace(tmp, src)
            return ("encoded", in_bytes, out_bytes, "")

        # Not worth it — keep the original bytes, but stamp the tag so the
        # next run doesn't redo the work. -c copy remux is near-instant.
        tmp.unlink(missing_ok=True)
        remux = [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-i", str(src), "-c", "copy",
            "-metadata", f"{TAG_KEY}={TAG_PREFIX}:kept-original",
            "-movflags", "+faststart",
            str(tmp),
        ]
        res = subprocess.run(remux, capture_output=True, text=True)
        if res.returncode == 0 and tmp.exists():
            os.replace(tmp, src)
            return ("kept", in_bytes, src.stat().st_size, "re-encode not smaller; tagged original")
        return ("kept", in_bytes, in_bytes, "re-encode not smaller (tag remux failed, will retry next run)")
    finally:
        tmp.unlink(missing_ok=True)


def fmt_gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crf", type=int, default=30, help="libx264 CRF (default 30; 33 is ~15%% smaller, visibly softer)")
    ap.add_argument("--workers", type=int, default=4, help="parallel ffmpeg processes (default 4)")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N pending videos")
    ap.add_argument("--dry-run", action="store_true", help="list what would be re-encoded, change nothing")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("[ERROR] ffmpeg/ffprobe not found on PATH.")
        sys.exit(1)
    if not MEDIA_DIR.exists():
        print(f"No media dir at {MEDIA_DIR} — nothing to do.")
        return

    videos = sorted(p for p in MEDIA_DIR.rglob("*.mp4") if not p.name.startswith("."))
    print(f"Media dir: {MEDIA_DIR}")
    print(f"Found {len(videos)} mp4 files, checking which are still pending...")

    pending = []
    skipped = 0
    with ThreadPoolExecutor(max_workers=max(args.workers * 2, 4)) as ex:
        for path, info in zip(videos, ex.map(probe, videos)):
            if already_done(info):
                skipped += 1
            else:
                pending.append(path)
    if args.limit is not None:
        pending = pending[: args.limit]
    pending_bytes = sum(p.stat().st_size for p in pending)
    print(f"Pending: {len(pending)} files, {fmt_gb(pending_bytes)}  (already done: {skipped})")

    if args.dry_run:
        for p in pending:
            print(f"  would re-encode {p.relative_to(MEDIA_DIR)}  ({p.stat().st_size / 1e6:.1f} MB)")
        return
    if not pending:
        return

    totals = {"encoded": 0, "kept": 0, "skipped": 0, "failed": 0}
    in_total = out_total = 0
    failures = []
    started = time.time()
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(encode, p, args.crf): p for p in pending}
        for fut in as_completed(futures):
            path = futures[fut]
            rel = path.relative_to(MEDIA_DIR)
            try:
                status, in_b, out_b, detail = fut.result()
            except Exception as e:  # noqa: BLE001 — one bad file must not stop the run
                status, in_b, out_b, detail = "failed", path.stat().st_size, path.stat().st_size, repr(e)
            totals[status] += 1
            in_total += in_b
            out_total += out_b
            done += 1
            if status == "failed":
                failures.append((rel, detail))
            elapsed = time.time() - started
            rate = done / elapsed if elapsed else 0
            eta = (len(pending) - done) / rate if rate else 0
            saved_pct = (100 - 100 * out_total / in_total) if in_total else 0
            print(
                f"[{done}/{len(pending)}] {status:7s} {rel}  "
                f"{in_b / 1e6:.1f} -> {out_b / 1e6:.1f} MB  "
                f"| total saved {saved_pct:.0f}%  eta {eta / 60:.0f} min"
                + (f"  ({detail})" if detail and status != "encoded" else "")
            )

    print()
    print("=" * 60)
    print(f"Done in {(time.time() - started) / 60:.1f} min")
    print(f"  encoded: {totals['encoded']}   kept-original: {totals['kept']}   "
          f"skipped: {totals['skipped']}   failed: {totals['failed']}")
    print(f"  {fmt_gb(in_total)} -> {fmt_gb(out_total)}  (saved {fmt_gb(in_total - out_total)})")
    if failures:
        print("\nFailed files (originals untouched — re-run to retry):")
        for rel, detail in failures:
            print(f"  {rel}: {detail}")


if __name__ == "__main__":
    main()
