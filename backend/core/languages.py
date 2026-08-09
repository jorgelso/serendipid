#!/usr/bin/env python3
"""
Content language detection for the SuperBrain analysis pipeline.

Separate axis from category — "language learning" (category) is about a post
teaching a language; this field is about what language the post's own content
is actually in. A German hiking vlog is category=outdoors & adventure,
language=German, not language learning.

Usually a single language, occasionally two for genuinely bilingual/
code-switching content (e.g. on-screen captions in a different language than
the speech) — parse_languages() supports a short list for that case, but the
prompt steers the model toward picking one unless the content is truly mixed.
"""

import re

LANGUAGES = [
    "english",
    "german",
    "italian",
    "spanish",
    "other",
    "no dialogue / visual only",
]

_LANGUAGE_BY_LOWER = {l.lower(): l for l in LANGUAGES}

LANGUAGE_PROMPT = f"""[Identify the language(s) actually spoken or shown on-screen in the content
itself — from the audio transcription's detected language and any on-screen
text found in the visual analysis. Do NOT use the original post caption's
language as evidence — captions are frequently written in a different
language than the content, or are unrelated to the content entirely (e.g. a
Japanese caption on an English-language video). List just one language
unless the content is genuinely bilingual (e.g. speech in one language with
on-screen captions in another) — comma-separated if so. Choose only from this
list (use these exact labels):
{', '.join(LANGUAGES)}
Use "no dialogue / visual only" for silent or music-only content with no
speech and no readable on-screen text. Use "other" only for a language
outside this list — do not guess if the evidence is too thin to tell.]"""


def parse_languages(raw: str) -> list:
    """Parse a raw LANGUAGE field into a deduplicated list of valid language
    labels, in order of first appearance. Word-boundary anchored so a short
    label can't false-positive inside an unrelated word."""
    if not raw:
        return []
    lower = raw.lower()
    found = []  # (position, canonical_label)
    for label in sorted(LANGUAGES, key=len, reverse=True):
        canonical = _LANGUAGE_BY_LOWER[label.lower()]
        if canonical in (c for _, c in found):
            continue
        m = re.search(r'\b' + re.escape(label.lower()) + r'\b', lower)
        if not m:
            continue
        found.append((m.start(), canonical))
        lower = lower[:m.start()] + (" " * len(label)) + lower[m.end():]
    found.sort(key=lambda x: x[0])
    return [c for _, c in found]
