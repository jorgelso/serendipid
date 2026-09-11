#!/usr/bin/env python3
"""
Manual media drop-off for posts Instagram refuses to serve.

instagram/instagram_downloader.py is the normal way media reaches the
pipeline, but a post that is rate-limited, login-walled, or gone can never
be downloaded — main.py exits 2 (queued for a retry that keeps failing) or
1, and the reel stays stuck forever. This module is the escape hatch behind
POST /manual-upload: the user gets the video some other way and hands it
over directly.

The only thing the rest of the pipeline actually depends on is the *shape*
of the folder main.py globs after its download step — <name>.mp4 /
<name>_audio.mp3 / <name>.jpg / info.txt under temp/. So that's all this
builds. main.py --media-folder then picks it up with no other change, and
core/media_store.py relocates it into media/<shortcode>/ afterwards exactly
as it would a real download.

Two normalizations happen on the way in, both because "whatever file I
could get" is the whole point of this path and it won't always be an
Instagram-shaped .mp4:

- Video is remuxed (or, failing that, re-encoded) to real MP4, because
  main.py globs `*.mp4` and analyzers/visual_analyze.py opens it with cv2 —
  a .mov/.webm merely renamed to .mp4 is a coin flip there.
- Images are re-encoded to real JPEG for the same reason (`*.jpg` glob).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(BACKEND_DIR / "temp")))

# Same trick instagram/instagram_downloader.py uses on itself: keep the
# backend root importable so `from instagram...` below resolves whether this
# module is imported by api.py (cwd = backend root) or run directly.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Deliberately narrow: these are the containers a person realistically ends
# up with after saving a reel by hand (phone screen recording, yt-dlp, a
# re-share). Anything else is rejected loudly rather than fed to ffmpeg on
# the off chance it works.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Upper bound on an accepted upload. A reel is single-digit MB; this is
# loose enough for a long uncompressed screen recording and tight enough
# that a misdirected upload can't fill the disk.
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


class ManualMediaError(Exception):
    """Raised when an uploaded file can't be turned into a usable folder."""


def _safe_stem(shortcode: str) -> str:
    """Filesystem-safe base name for the generated files.

    Unlike the downloader's caption-derived folder names, this is keyed on
    the shortcode: there's no caption to derive from here, and the
    shortcode is the one identifier that's already unique per post.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", shortcode) or "manual_post"


def _unique_folder(base: Path, name: str) -> Path:
    """Return a fresh directory under *base*, suffixing on collision."""
    folder = base / name
    counter = 1
    while folder.exists():
        folder = base / f"{name}_{counter}"
        counter += 1
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _run_ffmpeg(args: list) -> bool:
    """Run ffmpeg, returning True only if it produced a non-trivial file."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", *args],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
    except FileNotFoundError:
        raise ManualMediaError(
            "ffmpeg is not installed on the backend host — it's required to "
            "normalize a manually uploaded file."
        )
    if proc.returncode != 0:
        print(f"  ⚠ ffmpeg failed ({proc.returncode}): {proc.stderr[-400:]}")
        return False
    out = Path(args[-1])
    return out.exists() and out.stat().st_size > 1024


def _write_video(folder: Path, stem: str, data: bytes, suffix: str) -> Path:
    """Write *data* into *folder* as a real .mp4, converting if needed."""
    target = folder / f"{stem}.mp4"

    if suffix == ".mp4":
        target.write_bytes(data)
        return target

    source = folder / f"_upload{suffix}"
    source.write_bytes(data)
    try:
        # Remux first — a container swap with no re-encode, near-instant and
        # lossless. Falls through to a real transcode when the source codecs
        # aren't legal in MP4 (VP9/Opus out of a .webm being the common case).
        print(f"  Remuxing {suffix} → .mp4...")
        if not _run_ffmpeg(["-i", str(source), "-c", "copy", str(target)]):
            print("  Remux not possible — re-encoding instead (slower)...")
            target.unlink(missing_ok=True)
            if not _run_ffmpeg([
                "-i", str(source),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(target),
            ]):
                raise ManualMediaError(
                    f"Could not convert the uploaded {suffix} file to MP4. "
                    "Try uploading an .mp4 instead."
                )
    finally:
        source.unlink(missing_ok=True)
    return target


def _write_image(folder: Path, stem: str, data: bytes, suffix: str) -> Path:
    """Write *data* into *folder* as a real .jpg, converting if needed."""
    target = folder / f"{stem}.jpg"
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        # JPEG has no alpha channel; flattening onto white matches what a
        # screenshot of the post would have looked like anyway.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
        else:
            img = img.convert("RGB")
        img.save(target, "JPEG", quality=90)
    except ImportError:
        if suffix not in (".jpg", ".jpeg"):
            raise ManualMediaError(
                f"Pillow is not available to convert a {suffix} image to JPEG. "
                "Upload a .jpg instead."
            )
        target.write_bytes(data)
    except Exception as e:
        raise ManualMediaError(f"Could not read the uploaded image: {e}")
    return target


def _write_info_txt(folder: Path, url: str, caption: str, username: str,
                    is_video: bool) -> None:
    """Write the info.txt main.py's parse_info_txt() reads back.

    Format is copied from instagram_downloader.py's own info.txt writer —
    parse_info_txt() matches it with regexes, so the separator lines and
    the `Caption:` block's surrounding dashes are load-bearing, not
    decoration. `Date:` is deliberately omitted rather than faked: a
    manual upload has no reliable publish date, and an absent line leaves
    post_date NULL instead of stamping a wrong one.
    """
    lines = [
        "Instagram Post Information",
        "=" * 50,
        "",
        f"URL: {url}",
    ]
    if username:
        lines.append(f"Username: @{username.lstrip('@')}")
    lines += [
        "Likes: 0",
        f"Type: {'Video' if is_video else 'Image'}",
        "",
        "Caption:",
        "-" * 50,
        caption.strip() if caption.strip() else "No caption",
        "-" * 50,
        "",
    ]

    hashtags = re.findall(r"#\w+", caption or "")
    if hashtags:
        lines += ["Hashtags:", ", ".join(hashtags), ""]

    (folder / "info.txt").write_text("\n".join(lines), encoding="utf-8")


def prepare_manual_media_folder(shortcode: str, url: str, filename: str,
                                data: bytes, caption: str = "",
                                username: str = "") -> Path:
    """Build a temp/ folder from a hand-supplied file, shaped like a download.

    Returns the folder path, ready to be passed to `main.py --media-folder`.
    Raises ManualMediaError with a user-facing message on bad input.
    """
    if not data:
        raise ManualMediaError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ManualMediaError(
            f"That file is {len(data) / 1024 / 1024:.0f} MB — the limit is "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )

    suffix = Path(filename or "").suffix.lower()
    is_video = suffix in VIDEO_EXTENSIONS
    is_image = suffix in IMAGE_EXTENSIONS
    if not (is_video or is_image):
        raise ManualMediaError(
            f"Unsupported file type '{suffix or filename}'. Upload a video "
            f"({', '.join(sorted(VIDEO_EXTENSIONS))}) or an image "
            f"({', '.join(sorted(IMAGE_EXTENSIONS))})."
        )

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(shortcode)
    folder = _unique_folder(TEMP_DIR, f"manual_{stem}")

    try:
        if is_video:
            video_path = _write_video(folder, stem, data, suffix)
            # Same audio sidecar the downloader produces — main.py globs
            # `*_audio.mp3` for Whisper and Shazam, and a reel with no
            # transcript is most of the analysis missing. A silent video
            # simply yields no file, which the pipeline already handles.
            from instagram.instagram_downloader import extract_audio_from_video
            extract_audio_from_video(str(video_path),
                                     str(folder / f"{stem}_audio.mp3"))
        else:
            _write_image(folder, stem, data, suffix)

        _write_info_txt(folder, url, caption, username, is_video)
    except Exception:
        # Never leave a half-built folder behind — main.py would glob it and
        # analyze whatever happened to land there before the failure.
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise

    print(f"✓ Manual media prepared: {folder}")
    return folder


if __name__ == "__main__":
    # Smoke test: python core/manual_media.py <shortcode> <file>
    if len(sys.argv) < 3:
        print("usage: manual_media.py <shortcode> <media-file>")
        sys.exit(1)
    _sc, _path = sys.argv[1], Path(sys.argv[2])
    _folder = prepare_manual_media_folder(
        _sc, f"https://www.instagram.com/reel/{_sc}/",
        _path.name, _path.read_bytes(), caption="manual smoke test",
    )
    print("\n".join(sorted(p.name for p in _folder.iterdir())))
