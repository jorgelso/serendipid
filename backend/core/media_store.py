#!/usr/bin/env python3
"""
Permanent media storage for analyzed posts.

instagram_downloader.py downloads into temp/<caption-derived-folder>/ — a
transient, caption-named location with no link back to the post in the
database. Once analysis succeeds, relocate_to_media_store() moves those files
into media/<shortcode>/, a stable location keyed by the one identifier that
never changes, and returns the filenames so the caller can record them on the
post's DB row. The frontend can then serve /media/<shortcode>/<file> to watch
the original video without depending on Instagram still hosting it.

Files are renamed to generic names during the move (video.mp4, audio.mp3,
thumbnail.jpg, or 1.mp4/1.jpg/2.mp4/... for carousels) instead of keeping
their caption-derived names, since caption text often contains characters
(#, spaces, non-ASCII) that are awkward in a URL path.
"""

import os
import re
import shutil
from pathlib import Path

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", str(Path(__file__).resolve().parent.parent / "media")))

_CAROUSEL_AUDIO_RE = re.compile(r"_(\d+)_audio\.mp3$", re.IGNORECASE)
_CAROUSEL_VIDEO_RE = re.compile(r"_(\d+)\.mp4$", re.IGNORECASE)
_CAROUSEL_IMAGE_RE = re.compile(r"_(\d+)\.jpg$", re.IGNORECASE)


def _generic_name(filename: str) -> str:
    """Map a caption-derived download filename to a stable generic one."""
    m = _CAROUSEL_AUDIO_RE.search(filename)
    if m:
        return f"{m.group(1)}_audio.mp3"
    if filename.lower().endswith("_audio.mp3"):
        return "audio.mp3"
    if filename.lower().endswith("_thumbnail.jpg"):
        return "thumbnail.jpg"
    m = _CAROUSEL_VIDEO_RE.search(filename)
    if m:
        return f"{m.group(1)}.mp4"
    if filename.lower().endswith(".mp4"):
        return "video.mp4"
    m = _CAROUSEL_IMAGE_RE.search(filename)
    if m:
        return f"{m.group(1)}.jpg"
    if filename.lower().endswith(".jpg"):
        return "image.jpg"
    if filename == "info.txt":
        return "info.txt"
    # Unrecognized file — keep it, but don't lose it.
    return filename


def relocate_to_media_store(temp_folder, shortcode: str) -> list:
    """Move every file from *temp_folder* into media/<shortcode>/, renaming
    to generic filenames. Returns the list of filenames now under
    media/<shortcode>/ (relative, suitable for building /media/<shortcode>/<f>
    URLs), or [] if temp_folder doesn't exist or is empty.

    Removes temp_folder afterward if it ends up empty. Leaves it in place
    (with whatever couldn't be moved) if something goes wrong, rather than
    risking data loss — this is the one copy of the original download until
    the move succeeds.
    """
    src = Path(temp_folder)
    if not src.exists() or not src.is_dir():
        return []

    dest = MEDIA_DIR / shortcode
    dest.mkdir(parents=True, exist_ok=True)

    moved = []
    for item in sorted(src.iterdir()):
        if not item.is_file():
            continue
        dest_name = _generic_name(item.name)
        dest_path = dest / dest_name
        try:
            shutil.move(str(item), str(dest_path))
            moved.append(dest_name)
        except Exception as e:
            print(f"⚠️  Could not relocate {item.name} to media store: {e}")

    try:
        if not any(src.iterdir()):
            src.rmdir()
    except Exception:
        pass  # non-empty or in-use — leave it, not worth failing the save over

    return moved
