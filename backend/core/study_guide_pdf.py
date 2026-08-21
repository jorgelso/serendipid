"""
PDF rendering for study guides (core/study_guide.py).

Every saved study guide can be viewed/downloaded as a PDF
(GET /study-guides/{id}/pdf) and the collections list shows a thumbnail of
each guide's first page (GET /study-guides/{id}/thumbnail). Both are
rendered on demand from the stored markdown `content` rather than persisted
as separate files — cheap, deterministic (pure rendering, no LLM call), and
always in sync with the stored text; nothing to clean up if a guide is ever
deleted.

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

import html as html_module

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


def render_study_guide_pdf(title: str, content: str) -> bytes:
    """Render a study guide's markdown content to a PDF, returned as bytes."""
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

    pdf_bytes = render_study_guide_pdf(title, content)
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()
