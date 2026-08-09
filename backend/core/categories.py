#!/usr/bin/env python3
"""
Canonical content categories for the SuperBrain analysis pipeline.

A single post can genuinely belong to more than one category (a meme built
around a philosophy quote is both "humor & memes" and "personal reflection &
philosophy"). Every analyzer (Instagram, YouTube, web page) pulls its
CATEGORY prompt text from CATEGORY_PROMPT and validates model output through
parse_categories() so results stay consistent across pipelines instead of
each prompt drifting its own list over time.
"""

import re

CATEGORIES = [
    "product",
    "places",
    "outdoors & adventure",
    "fitness",
    "food",
    "book",
    "film",
    "tv shows",
    "event",
    "software & tech",
    "learning & study techniques",
    "language learning",
    "psychology & mindset",
    "personal reflection & philosophy",
    "science & research",
    "religion & spirituality",
    "politics & society",
    "art, design & photography",
    "music",
    "humor & memes",
    "surveillance, psyops & government conspiracy",
    "lifestyle & clean living",
    "ai ethics & tech skepticism",
    "environment & sustainability",
    "other",
]

_CATEGORY_BY_LOWER = {c.lower(): c for c in CATEGORIES}

CATEGORY_PROMPT = f"""[List 1-3 categories that genuinely fit this content, separated by commas.
A post can span more than one category — e.g. a meme built around a philosophy
quote is both "humor & memes" and "personal reflection & philosophy". Do not
force a fit: only list a category if the content is actually about it. Choose
only from this list (use these exact labels):
{', '.join(CATEGORIES)}
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
    lower = raw.lower()
    found = []  # (position, canonical_label)
    for label in sorted(CATEGORIES, key=len, reverse=True):
        canonical = _CATEGORY_BY_LOWER[label.lower()]
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
# multi-category answer the model already gave.
_KEYWORD_CATEGORIES = {
    "product": ["camera", "device", "gadget", "phone", "laptop", "unbox", "dji", "osmo", "action cam", "review"],
    "places": ["travel", "destination", "village", "city", "itinerary", "landmark"],
    "outdoors & adventure": ["hike", "hiking", "trek", "camping", "trail", "mountain", "backpacking", "climb"],
    "fitness": ["workout", "exercise", "gym", "calisthenics", "training", "muscle", "cardio", "yoga"],
    "food": ["recipe", "cooking", "ingredients", "restaurant", "cuisine", "dish", "bake"],
    "book": ["book", "novel", "author", "literature", "chapter"],
    "film": ["movie", "cinema", "actor", "director", "trailer"],
    "tv shows": ["series", "episode", "season", "netflix", "tv show"],
    "event": ["concert", "festival", "conference", "meetup"],
    "software & tech": ["app", "software", "code", "programming", "api", "python", "javascript", "ai tool"],
    "learning & study techniques": ["study", "memorization", "mnemonic", "study hack", "exam"],
    "language learning": ["language learning", "vocabulary", "grammar", "translation"],
    "psychology & mindset": ["mindset", "cognitive", "mental health", "psychology", "resilience"],
    "personal reflection & philosophy": ["philosophy", "existential", "reflection", "life lesson"],
    "science & research": ["study finds", "research", "researchers", "peer-reviewed", "scientists"],
    "religion & spirituality": ["prayer", "bible", "faith", "god", "spiritual"],
    "politics & society": ["government", "election", "policy", "protest", "society"],
    "art, design & photography": ["photography", "camera settings", "design", "illustration", "painting"],
    "music": ["song release", "album", "musician", "concert tour"],
    "humor & memes": ["meme", "joke", "funny", "relatable"],
    "surveillance, psyops & government conspiracy": ["surveillance", "psyop", "psyops", "cia", "deep state", "mass surveillance", "propaganda", "cover-up", "whistleblower"],
    "lifestyle & clean living": ["detox", "microplastic", "toxin", "clean eating", "non-toxic", "pantry swap", "endocrine disruptor"],
    "ai ethics & tech skepticism": ["ai risk", "artificial intelligence", "ai ethics", "against ai", "ai backlash", "big tech"],
    "environment & sustainability": ["climate", "sustainability", "pollution", "eco-friendly", "environment", "carbon footprint", "renewable"],
}


def keyword_fallback_categories(text: str) -> list:
    """Score keyword hits against *text* and return categories with at least
    one match, ranked by hit count (used only when the model gave no usable
    CATEGORY field at all)."""
    low = text.lower()
    scored = []
    for category, keywords in _KEYWORD_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in low)
        if score > 0:
            scored.append((score, category))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:3]] or ["other"]
