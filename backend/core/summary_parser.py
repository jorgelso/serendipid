#!/usr/bin/env python3
"""
Pure parsing/prompt-building helpers for the analysis pipeline's AI calls —
both building the combined title/summary/tags/music/category/language prompt
(build_final_summary_prompt()) and parsing its output (parse_summary()).

Lives in core/ (not main.py) specifically so core/batch_processor.py can
reuse it without importing main.py — api.py deliberately never imports
main.py (see backend/CLAUDE.md's subprocess-decoupling note: main.py always
runs as a spawned subprocess so a crash/hang there can't take down the API
process), and that boundary should hold even though ANALYSIS_MODE=batch's
resumption logic runs in-process in api.py.
"""

import re

from core.categories import category_prompt, parse_categories, keyword_fallback_categories
from core.languages import language_prompt, parse_languages


def _extract_section(output: str, marker: str) -> str:
    """Extract the content after a section marker, stopping at the next divider."""
    if marker not in output:
        return output[:2000]
    after = output.split(marker, 1)[1]
    lines = after.split("\n")
    content_lines = []
    started = False
    for line in lines:
        stripped = line.strip('-').strip('=').strip('─').strip()
        if not started:
            # Skip blank lines and pure divider lines
            if stripped:
                started = True
                content_lines.append(line)
        else:
            # Stop at a divider line (5+ repeated chars)
            raw = line.strip()
            if (raw.startswith('─' * 5) or raw.startswith('-' * 5) or
                    raw.startswith('=' * 5) or raw.startswith('*' * 5)):
                break
            content_lines.append(line)
    return "\n".join(content_lines).strip()


def _clean_visual(output: str) -> str:
    return _extract_section(output, "📝 ANALYSIS:")


def _clean_audio(output: str) -> str:
    return _extract_section(output, "📝 TRANSCRIBED TEXT:")


def _clean_text(output: str) -> str:
    return _extract_section(output, "🔍 ANALYSIS:")


def build_final_summary_prompt(results, instagram_url, source_caption="", source_hashtags=None):
    """Build the combined title/summary/tags/music/category/language prompt
    from all analysis results. Pure (no I/O) — shared by main.py's immediate
    pipeline (generate_final_summary()) and core/batch_processor.py's
    analysis-phase resumption, which submits this exact prompt to a batch
    job instead of calling the router synchronously."""
    # Collect all analysis data
    visual_summary = ""
    audio_summary = ""
    music_info = ""
    text_summary = ""

    # Extract visual analysis
    if results['visual']:
        visual_summary = "VISUAL ANALYSIS:\n"
        for item in results['visual']:
            output = item['output']
            clean = _clean_visual(output)
            if clean:
                visual_summary += f"- {clean[:600]}\n"

    # Extract audio transcription
    if results['audio_transcription']:
        audio_summary = "AUDIO TRANSCRIPTION:\n"
        for item in results['audio_transcription']:
            output = item['output']
            clean = _clean_audio(output)
            lang = output.split('Detected Language:')[1].split('(')[0].strip() if 'Detected Language:' in output else 'Unknown'
            audio_summary += f"- Language: {lang}\n"
            if clean:
                # Was [:400] through analysis_version 8, which cut most
                # talking-head reels off mid-sentence — see version 9 in
                # core/database.py.
                audio_summary += f"- Content: {clean[:3000]}\n"

    # Extract music identification
    if results['music_identification']:
        music_info = "MUSIC:\n"
        for item in results['music_identification']:
            output = item['output']
            if 'Song:' in output:
                song_line = [line for line in output.split('\n') if 'Song:' in line][0]
                artist_line = [line for line in output.split('\n') if 'Artist:' in line]

                song = song_line.split('Song:')[1].strip()
                artist = artist_line[0].split('Artist:')[1].strip() if artist_line else 'Unknown'
                music_info += f"- {song} by {artist}\n"
            elif 'No match found' in output:
                music_info += "- No music identified (likely voiceover/no background music)\n"

    # Extract text analysis
    if results['text']:
        text_summary = "TEXT ANALYSIS:\n"
        for item in results['text']:
            clean = _clean_text(item['output'])
            if clean:
                text_summary += f"{clean[:600]}\n"

    # Extract original caption/hashtags (from the source export, if provided)
    caption_block = ""
    if source_caption and source_caption.strip():
        caption_block = f"ORIGINAL POST CAPTION (unverified — may be irrelevant or spam, see instructions below):\n{source_caption.strip()}\n"

    hashtags_block = ""
    if source_hashtags:
        hashtags_block = f"ORIGINAL POST HASHTAGS: {' '.join('#' + h.lstrip('#') for h in source_hashtags)}\n"

    # Combine all information
    combined_info = f"""
INSTAGRAM POST: {instagram_url}

{caption_block}
{hashtags_block}

{visual_summary}

{audio_summary}

{music_info}

{text_summary}
"""

    # Generate structured summary using LLM
    prompt = f"""Based on the following analysis of an Instagram post, create a detailed structured summary that preserves every concrete, useful detail found below — not just a thematic overview.

{combined_info}

BEFORE YOU WRITE ANYTHING: compare the ORIGINAL POST CAPTION/HASHTAGS above to the VISUAL ANALYSIS / AUDIO TRANSCRIPTION / TEXT ANALYSIS above, and classify the relationship into exactly one of these three cases:

1. CONSISTENT — the caption describes, adds detail to, or is simply narrower/broader than what the media shows (e.g. a 10-second clip of a finished dish while the caption gives the full recipe; a short personal clip with a caption telling the actual story; generic/ambient b-roll — walking, a talking-head, a plain product shot, a static single image — paired with a caption that supplies the real substance). This is extremely common and completely legitimate: plenty of real posts put the actual information in the text and use the video only as illustration or a hook, especially on short clips. Thin, generic, or non-specific media is NOT a sign of mismatch — it's normal, and the caption should be trusted and used normally.
2. GENUINE MISMATCH — the media itself shows a different, specific, self-contained subject that competes with and contradicts the caption: e.g. a screenshot of a different, identifiable social media post/account, a named person/place/event/object visibly different from what the caption claims, or on-screen text/speech that is clearly about an unrelated topic. The key test is not "does the media lack detail the caption has" — it's "does the media affirmatively show something else specific." This is a known spam pattern (pairing a caption about a trending topic with an unrelated 'hook' video to farm reach) but it is the exception, not the default assumption.
3. UNCLEAR — the media analysis is too thin/generic to tell either way. Treat this the same as CONSISTENT (trust the caption) — do not treat ambiguity as evidence of a mismatch.

Only for case 2 (GENUINE MISMATCH): build the TITLE, SUMMARY, and TAGS from what the visual/audio/text analysis actually shows, not from the caption, and add one short line at the end of the SUMMARY noting the mismatch plainly, e.g. "Note: this post's caption describes [caption topic], but the video/image itself actually shows [actual content] — caption and media do not match, likely mismatched/bait content." For cases 1 and 3, use the caption normally as you would for any post — do not add a mismatch note or second-guess a caption just because the video accompanying it is short, generic, or low on independently-verifiable detail.

Generate a report in this EXACT format:

📌 TITLE:
[Create a clear, descriptive title. Use the caption normally unless the classification above is GENUINE MISMATCH, in which case title this from what the media actually shows instead.]

📝 SUMMARY:
[A detailed summary — as long as it needs to be to capture the real content, not capped at a fixed sentence count. Include:
- Main content/theme
- Every specific, concrete detail found in the analysis above: exact ingredients/quantities, step-by-step instructions in order, specific locations/names/prices, tool/product names, numbers, measurements, links. Reproduce these specifics directly — do not paraphrase them away into vague generalities like "key ingredients" or "several steps."
- If this is a tutorial, recipe, itinerary, or how-to, list out the actual steps/items found in the analysis above, in order, not just a description that steps exist.
- Important highlights
- Any actionable items or recommendations
Only include details that are actually present in the analysis above — do not invent or guess specifics that weren't captured by the visual/audio analysis. If the analysis above is thin (e.g. no clear speech was transcribed and no on-screen text was found), say so plainly rather than padding the summary with generic filler.
Do not mention the absence of structural elements that were never expected in the first place — e.g. don't say "no instructions were given" or "no steps are provided" for a meme, joke, photo, quote, or other content that isn't a tutorial/recipe/how-to. Only note what's missing when its absence is actually notable (e.g. a recipe video with no visible ingredient list). Never write a sentence whose only purpose is to point out that something isn't present.

Apply the classification from above: for CONSISTENT or UNCLEAR, use the caption normally, including as the primary source of detail when the media itself is thin (a short clip, a single generic shot) — that's a normal post, not a gap to flag. Only for GENUINE MISMATCH, describe what the visual/audio/text analysis actually shows and include the one-line mismatch note described above instead of the caption's claims.]

🏷️ TAGS:
[Generate 8-12 relevant hashtags/keywords. Use the caption's topic normally unless the classification above is GENUINE MISMATCH, in which case tag what the media actually shows instead.]

🎵 MUSIC:
[Music/song name if found, or "No background music" or "Voiceover only"]

📂 CATEGORY:
{category_prompt()}

🌐 LANGUAGE:
{language_prompt()}

Be specific and thorough — prioritize capturing concrete, actionable detail over brevity."""

    return prompt


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
