#!/usr/bin/env python3
"""
Canonical content categories for the Serendipid analysis pipeline.

A single post can genuinely belong to more than one category (a meme built
around a philosophy quote is both humor and philosophy). Every analyzer (Instagram, YouTube, web page) pulls its
CATEGORY prompt text from category_prompt() and validates model output through
parse_categories() so results stay consistent across pipelines instead of
each prompt drifting its own list over time.

The list itself is user-configurable (see core/app_config.py).
"""

import re

from core import app_config


def category_names() -> list:
    """The configured category labels (core/default_config.json, overridden
    by config/user_config.json; see core/app_config.py)."""
    return app_config.category_names()


def category_prompt() -> str:
    return f"""[List 1-3 categories that genuinely fit this content, separated by commas.
A post can span more than one category — e.g. a meme built around a philosophy
quote can fit both a humor category and a philosophy category. Do not
force a fit: only list a category if the content is actually about it. Choose
only from this list (use these exact labels):
{', '.join(category_names())}
Use "other" only when truly nothing above applies — it should be rare, never a
default pick because nothing seemed like an exact match.]"""


def parse_categories(raw: str) -> list:
    """Parse a raw CATEGORY field into a deduplicated list of valid category
    labels, in order of first appearance.

    Matches canonical labels directly against the raw text (longest label
    first) instead of splitting on delimiters — a delimiter split breaks
    labels that contain a comma themselves (e.g. "art, design & photography"
    would be mangled into unmatched "art" / "design & photography"
    fragments by a naive split on ','). Matching longest-first also means a
    compound label always wins over a shorter label that happens to be a
    substring of it.

    Matches are word-boundary anchored (\\b) rather than plain substring
    search, so a short label doesn't false-positive inside an unrelated
    longer word — e.g. plain substring search matches "other" inside
    "an-OTHER" or "book" inside "note-BOOK"; stray model prose like "this
    could also fit another category" would otherwise silently add "other".
    """
    if not raw:
        return []
    names = category_names()
    by_lower = {c.lower(): c for c in names}
    lower = raw.lower()
    found = []  # (position, canonical_label)
    for label in sorted(names, key=len, reverse=True):
        canonical = by_lower[label.lower()]
        if canonical in (c for _, c in found):
            continue
        m = re.search(r'\b' + re.escape(label.lower()) + r'\b', lower)
        if not m:
            continue
        found.append((m.start(), canonical))
        # Blank out the matched span so a shorter label contained within it
        # (e.g. "film" inside a longer already-matched phrase) can't also match.
        lower = lower[:m.start()] + (" " * len(label)) + lower[m.end():]
    found.sort(key=lambda x: x[0])
    return [c for _, c in found]


# Lightweight keyword fallback — only used when the model's CATEGORY field is
# missing/unparseable (e.g. malformed output), never to override a real
# multi-category answer the model already gave. Keywords come from each
# category's "keywords" list in the config.
def keyword_fallback_categories(text: str) -> list:
    """Score keyword hits against *text* and return categories with at least
    one match, ranked by hit count (used only when the model gave no usable
    CATEGORY field at all)."""
    low = text.lower()
    scored = []
    for category, keywords in app_config.category_keywords().items():
        score = sum(1 for kw in keywords if kw.lower() in low)
        if score > 0:
            scored.append((score, category))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:3]] or ["other"]
