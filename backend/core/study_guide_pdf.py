"""
PDF rendering for study guides (core/study_guide.py).

Every saved study guide can be viewed/downloaded as a PDF
(GET /study-guides/{id}/pdf) and the collections list shows a thumbnail of
each guide's first page (GET /study-guides/{id}/thumbnail). Both are
rendered from the stored markdown `content` — deterministic (pure
rendering, no LLM call) and always in sync with the stored text. PDFs are
rendered fresh per request; thumbnails are cached on disk (see
get_cached_study_guide_thumbnail) because the collections grid asks for a
whole page of them at once, on every visit.

All rendering is serialized behind _render_lock. WeasyPrint's native text
stack (Pango/HarfBuzz/fontconfig) and PyMuPDF are not thread-safe, and the
endpoints run renders via asyncio.to_thread — a collections page firing ~6
thumbnail requests at once had several renders running concurrently, which
segfaulted the whole API process (not a catchable Python exception).

Renders via WeasyPrint (markdown -> HTML -> a real CSS box layout), not
fpdf2's simplified write_html(). Two real bugs in the fpdf2 version drove
this switch, both found by inspecting actual generated guides, not
speculation:
  1. fpdf2's core PDF fonts only support Latin-1/WinAnsi — a single curly
     apostrophe in LLM output 500'd the endpoint outright. WeasyPrint does
     real Unicode text shaping, so this class of bug doesn't exist here —
     no sanitize-to-ASCII workaround needed (removed; see git history for
     the old _sanitize_for_pdf if this ever needs to be understood).
  2. fpdf2's write_html() has a page-break/list interaction bug: once an
     automatic page break lands inside a <ul>, several subsequent <li>
     items each got stranded alone on their own near-empty page before
     "recovering" — reproduced in isolation with plain short bullets (no
     bold, no citations, no wrapping needed to trigger it), confirmed on
     real generated guides (one had 4 consecutive single-bullet pages).
     WeasyPrint's real CSS layout engine doesn't have this bug — verified
     against the same real guides, page density is now consistent
     throughout with no stranded single-line pages.
"""

import hashlib
import html as html_module
import os
import threading
from pathlib import Path

import markdown
from weasyprint import HTML

# Deliberately plain, readable, and print-safe — this is a reference
# document meant to be read or printed, not a branded artifact. orphans/
# widows prevents a single stranded line at the top/bottom of a page (the
# CSS-spec-correct version of the problem the old fpdf2 renderer had no
# way to avoid at all).
_PDF_CSS = """
@page { size: A4; margin: 2.2cm; }
body {
  font-family: "Helvetica Neue", Helvetica, Arial, "Segoe UI", sans-serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #1a1a1a;
}
h1 { font-size: 20pt; margin: 0 0 0.5em; }
h2 { font-size: 15pt; margin: 1.3em 0 0.5em; }
h3, h4, h5, h6 { font-size: 12pt; margin: 1em 0 0.4em; }
p, li { orphans: 3; widows: 3; }
ul, ol { margin: 0.3em 0 0.9em; padding-left: 1.4em; }
li { margin-bottom: 0.45em; }
blockquote {
  margin: 0.8em 0; padding-left: 0.9em;
  border-left: 3px solid #cccccc; color: #444444;
}
code { background: #f0f0f0; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.9em; }
hr { border: none; border-top: 1px solid #dddddd; margin: 1.2em 0; }
a { color: #1a1a1a; }
"""


# One process-wide lock for every WeasyPrint/PyMuPDF call — see the module
# docstring for the segfault this prevents.
_render_lock = threading.Lock()

_THUMBNAIL_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "study_guide_thumbnails"


def render_study_guide_pdf(title: str, content: str) -> bytes:
    """Render a study guide's markdown content to a PDF, returned as bytes."""
    with _render_lock:
        return _render_pdf_unlocked(title, content)


def _render_pdf_unlocked(title: str, content: str) -> bytes:
    body_html = markdown.markdown(content or "", extensions=["extra", "sane_lists"])
    doc_title = html_module.escape(title or "Study Guide")
    full_html = f"<html><head><title>{doc_title}</title><style>{_PDF_CSS}</style></head><body>{body_html}</body></html>"
    return HTML(string=full_html).write_pdf()


def render_study_guide_thumbnail(title: str, content: str, dpi: int = 96) -> bytes:
    """Rasterize the first page of a study guide's PDF to a PNG — used for
    the collection view's grid of thumbnails. Imports pymupdf lazily so a
    backend without it installed only fails when a thumbnail is actually
    requested, not on module import.
    """
    import pymupdf

    with _render_lock:
        pdf_bytes = _render_pdf_unlocked(title, content)
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=dpi)
            return pix.tobytes("png")
        finally:
            doc.close()


def get_cached_study_guide_thumbnail(study_guide_id: int, title: str, content: str, dpi: int = 96) -> bytes:
    """render_study_guide_thumbnail, cached on disk as
    cache/study_guide_thumbnails/<id>-<hash>.png.

    The hash covers everything that affects the rendered image (title,
    content, CSS, dpi), so a changed guide or stylesheet just misses the
    cache — no invalidation hooks needed elsewhere. The id prefix is only so
    older variants of the same guide can be cleaned up when a new one is
    written.
    """
    digest = hashlib.sha256(
        "\0".join([title or "", content or "", _PDF_CSS, str(dpi)]).encode("utf-8")
    ).hexdigest()[:32]
    path = _THUMBNAIL_CACHE_DIR / f"{study_guide_id}-{digest}.png"
    try:
        return path.read_bytes()
    except FileNotFoundError:
        pass

    png_bytes = render_study_guide_thumbnail(title, content, dpi=dpi)

    # Cache writes are best-effort: a failure here should never fail the
    # request that already has its PNG in hand.
    try:
        _THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for stale in _THUMBNAIL_CACHE_DIR.glob(f"{study_guide_id}-*.png"):
            if stale != path:
                stale.unlink(missing_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(png_bytes)
        os.replace(tmp, path)
    except OSError as e:
        print(f"[WARNING]  Could not cache study guide thumbnail {path.name}: {e}")
    return png_bytes
