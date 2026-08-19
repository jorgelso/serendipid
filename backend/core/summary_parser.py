#!/usr/bin/env python3
"""
Pure parsing helpers for the combined title/summary/tags/music/category/
language AI output (see main.py's build_final_summary_prompt()).

Lives in core/ (not main.py) specifically so core/batch_processor.py can
reuse it without importing main.py — api.py deliberately never imports
main.py (see backend/CLAUDE.md's subprocess-decoupling note: main.py always
runs as a spawned subprocess so a crash/hang there can't take down the API
process), and that boundary should hold even though ANALYSIS_MODE=batch's
resumption logic runs in-process in api.py.
"""

import re

from core.categories import parse_categories, keyword_fallback_categories
from core.languages import parse_languages


def _parse_field(text: str, emoji: str, label: str) -> str:
    """
    Extract a field value from AI output — handles all common AI formatting variations:
      📌 TITLE: value
      📌 **TITLE:** value
      📌 **TITLE**  \n  value
    Also handles emoji variation selectors (U+FE0F) that may or may not be present.
    Returns the first non-empty content after the label, stopped at the next
    section emoji line or blank-line boundary.
    """
    # Strip variation selector from emoji so pattern works whether or not it's present
    emoji_base = emoji.replace('️', '')
    pattern = re.compile(
        rf'{re.escape(emoji_base)}️?\s*\*{{0,2}}{re.escape(label)}\*{{0,2}}:?\s*',
        re.IGNORECASE
    )
    m = pattern.search(text)
    # Fallback: model may output U+FFFD instead of the emoji (encoding mangling)
    if not m:
        pattern_fb = re.compile(
            rf'�\s*\*{{0,2}}{re.escape(label)}\*{{0,2}}:?\s*',
            re.IGNORECASE
        )
        m = pattern_fb.search(text)
    if not m:
        return ""
    after = text[m.end():]
    # Collect until next section (identified by an emoji at line start) or 2 blank lines
    lines = after.split('\n')
    content_lines = []
    for line in lines:
        stripped = line.strip()
        # Stop at next section header — match ANY emoji/symbol at line start,
        # OR a U+FFFD replacement char (model sometimes mangles lower-plane emojis)
        if content_lines and re.match(
            r'^[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U00002B00-\U00002BFF�]',
            stripped,
        ):
            break
        # Skip pure markdown bold/italic wrapper lines but keep the text
        content_lines.append(re.sub(r'\*{1,3}([^*]+?)\*{1,3}', r'\1',
                                      re.sub(r'^\*{1,3}|\*{1,3}$', '', stripped)))
    # Remove leading/trailing blank lines and join
    result = ' '.join(l for l in content_lines if l).strip()
    # Strip surrounding markdown bold (**)
    result = re.sub(r'^\*+|\*+$', '', result).strip('"').strip()
    return result


def parse_summary(summary_text):
    """
    Parse AI-generated summary to extract structured data.
    Robust against markdown bold, missing colons, varied whitespace.

    Returns:
        tuple: (title, summary, tags, music, category, language)
        category and language are each a list of 1+ labels — a post can
        belong to more than one category, and occasionally spans more than
        one language (e.g. speech in one language, captions in another).
        Importance is scored separately — see main.py's score_importance() —
        rather than parsed from this summary text.
    """
    title = ""
    summary = ""
    tags = []
    music = ""
    category = []
    language = []

    try:
        title   = _parse_field(summary_text, "📌", "TITLE")
        summary = _parse_field(summary_text, "📝", "SUMMARY")
        music   = _parse_field(summary_text, "🎵", "MUSIC")

        # Tags: grab block then split on whitespace/commas
        raw_tags = _parse_field(summary_text, "🏷️", "TAGS")
        if not raw_tags:  # try without variation selector
            raw_tags = _parse_field(summary_text, "🏷", "TAGS")
        if not raw_tags:  # model sometimes omits emoji entirely
            _tm = re.search(r'(?:^|\n)\s*\*{0,2}TAGS\*{0,2}:?\s*([^\n]+)', summary_text, re.IGNORECASE)
            if _tm:
                raw_tags = _tm.group(1).strip()
        if raw_tags:
            tags = [t.strip() for t in re.split(r'[\s,]+', raw_tags) if t.strip()]

        music = _parse_field(summary_text, "🎵", "MUSIC")
        if not music:
            _mm = re.search(r'(?:^|\n)\s*\*{0,2}MUSIC\*{0,2}:?\s*([^\n]+)', summary_text, re.IGNORECASE)
            if _mm:
                music = _mm.group(1).strip()

        # Category: one or more comma-separated labels
        raw_cat = _parse_field(summary_text, "📂", "CATEGORY")
        raw_cat = re.sub(r'\*+', '', raw_cat).strip()
        raw_cat = raw_cat.split('\n')[0].strip()
        category = parse_categories(raw_cat)

        # Language: one or more comma-separated labels (usually just one)
        raw_lang = _parse_field(summary_text, "🌐", "LANGUAGE")
        raw_lang = re.sub(r'\*+', '', raw_lang).strip()
        raw_lang = raw_lang.split('\n')[0].strip()
        language = parse_languages(raw_lang)

    except Exception as e:
        print(f"⚠️ Error parsing summary: {e}")

    # Fallback: only when the model's CATEGORY field was missing/unparseable
    # (never overrides a real answer the model already gave, even a single one).
    if not category:
        category = keyword_fallback_categories(f"{title} {summary} {' '.join(tags)} {summary_text}")

    # No keyword fallback for language — guessing a language from keywords is
    # unreliable, so an unparseable field is left empty (unknown) rather than
    # guessed.

    return title, summary, tags, music, category, language


def apply_music_override(music, music_identification_results):
    """Override the LLM's MUSIC field with direct Shazam output (preserves
    Spotify/Apple Music links the LLM would otherwise paraphrase away)."""
    if not music_identification_results:
        return music
    for item in music_identification_results:
        out = item['output']
        if 'Song:' in out:
            song = [l.split('Song:')[1].strip() for l in out.split('\n') if 'Song:' in l][0]
            artist_line = [l.split('Artist:')[1].strip() for l in out.split('\n') if 'Artist:' in l]
            artist = artist_line[0] if artist_line else 'Unknown'
            link = ""
            spot_line = [l.split('Spotify:')[1].strip() for l in out.split('\n') if 'Spotify:' in l]
            apple_line = [l.split('Apple Music:')[1].strip() for l in out.split('\n') if 'Apple Music:' in l]
            if spot_line:
                link = spot_line[0]
            elif apple_line:
                link = apple_line[0]
            music = f"{song} by {artist}"
            if link:
                music += f" | {link}"
            break
        elif 'No match found' in out:
            music = "No music identified"
            break
    return music
