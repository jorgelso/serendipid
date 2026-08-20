#!/usr/bin/env python3
"""
Eloquence judging for the "what should I watch to become more well-spoken"
feature — scores a post's audio_transcription for oratory eloquence,
independent of topic, format popularity, or how useful/correct the content is.

Calibrated against real saved posts (see ELOQUENCE_PROMPT below for the
reference cases baked into the rubric) rather than written in the abstract:
a graduation speech and an economics commentary were judged eloquent; a
red-team walkthrough that is clear, well-organized, and even explains *why*
the exploit worked was judged NOT eloquent, because clarity/organization
alone is not oratory craft. Several "3 steps to X" / "how hackers use Google"
style tutorials were judged not eloquent purely for being tutorials — except
neuroscience/psychology/self-improvement creators, who were judged to
generally speak in a genuinely well-spoken register even when the content is
structured as tips, so that genre is exempted from the tutorial default.

Unlike category/language, eloquence is scored in its own dedicated LLM call
(build_eloquence_prompt() + ModelRouter._openai_text(), pinned to OpenAI —
see scripts/score_eloquence.py) rather than spliced into the main analysis
prompt, same rationale as core/importance.py.

Candidates are pre-filtered in Python (not SQL) by transcript length and
filler-word ratio — validated during development against hand-labeled posts:
posts under the filler-ratio threshold that were still rambling/casual (not
"clean" walkthroughs) reliably scored NOT eloquent anyway, so the pre-filter
only exists to cut obviously-too-short/filler-heavy posts before spending an
LLM call, not to replace the judge's own discrimination.
"""

import re

FILLER_WORDS = {
    "like", "um", "uh", "you know", "kind of", "sort of",
    "basically", "literally", "actually", "i mean", "right",
}

# Candidates below this transcript length essentially never contain a
# sustained explanation (validated against hand-labeled short clips —
# see the Eileen Gu examples in development: even genuinely sharp short
# clips read as highlight fragments, not full videos worth recommending).
LENGTH_THRESHOLD = 800

# Filler-ratio ceiling for pre-filtering candidates — separates the clearest
# rambling/casual delivery (labeled "not eloquent" examples sat at 0.0356+)
# from clean delivery (labeled "eloquent" examples topped out at 0.0141).
FILLER_RATIO_THRESHOLD = 0.027

_WORD_RE = re.compile(r"[a-záéíóúñü']+")


def filler_ratio(text: str):
    """Fraction of words that are filler words, or None for empty text."""
    words = _WORD_RE.findall((text or "").lower())
    if not words:
        return None
    return sum(1 for w in words if w in FILLER_WORDS) / len(words)


def passes_prefilter(transcript: str) -> bool:
    """Cheap, free pre-filter applied before spending an LLM call — see
    module docstring. Does not replace the judge's own discrimination."""
    if not transcript or len(transcript) <= LENGTH_THRESHOLD:
        return False
    fr = filler_ratio(transcript)
    return fr is not None and fr < FILLER_RATIO_THRESHOLD


ELOQUENCE_PROMPT = """[You are judging a spoken-word transcript for ELOQUENCE IN THE ORATORY
SENSE — not for topic, not for how useful or correct the content is, and not
for whether the delivery is merely clear or well-organized on its own.
You're judging whether the person speaks in a genuinely well-spoken,
rhetorically skilled way — the way a good speech or commentary sounds, not
the way a tutorial or demo sounds.

The transcript may contain transcription artifacts (missing accents, a
garbled word, a duplicated sentence) — ignore these, judge the underlying
speech. The transcript may also reference visual content the audio alone
can't fully convey ("this one", "like this", "here you can see") — that is
completely fine and must NOT be penalized. You are only judging whether the
speaking itself is eloquent, not whether the transcript stands alone as text.

CRITERIA (weigh together):

1. Delivery mode: speech vs. tutorial.
   Is this delivered as a person making and developing a point — a
   commentary, an argument, a reflection — or is it a tutorial/how-to/
   procedural walkthrough ("Number one... Number two...", "First... Then...
   After that...", "let me show you...")?
   Tutorials and step-by-step walkthroughs default to NOT eloquent,
   regardless of how clear or well-organized they are. This default can only
   be overridden if the delivery itself shows real rhetorical craft (see #3)
   beyond just clean organization.
   EXCEPTION: this tutorial default applies to technical/procedural domains
   (software, cybersecurity, finance/trading mechanics, career "how-to"
   advice, and similar step-by-step instructional content). It does NOT
   apply to neuroscience, psychology, and self-improvement content — creators
   in that space tend to speak in a genuinely well-spoken, articulate
   register even when the content is organized as tips or steps, and that
   register is itself worth learning from for everyday conversation. For
   that domain, judge the actual delivery quality on its own merits (criteria
   2-4) rather than defaulting it to not-eloquent just for being structured
   as a list or a guide.

2. Explains why, not just what/how.
   Does the speaker reason toward causes, meaning, or implications — or do
   they just report steps taken or facts observed in sequence?

3. Oratory craft.
   Vocabulary precision, sentence variety, rhetorical technique (repetition,
   analogy, concrete imagery, a turn of phrase), specificity (named sources,
   real numbers, quotable lines). Being clear and well-organized is NOT
   sufficient by itself — a technically clean, logically sequenced
   explanation with zero rhetorical craft is still not eloquent.
   Reference case: a red-team walkthrough that clearly explains each step of
   a cloud exploit and even recaps *why* it worked at the end is still not
   eloquent — it's flat, plain, procedural delivery with no oratory quality.

4. Synthesis / payoff.
   Does the speaker land on a closing insight that ties the piece together,
   or does it just stop, trail into a call-to-action ("comment X and I'll
   send it"), or end on a throwaway aside/joke?

OUTPUT FORMAT (exactly):
VERDICT: YES or NO
TUTORIAL: YES or NO (is this delivered as a tutorial/how-to/procedural
  walkthrough, per criterion 1 — answer this regardless of what VERDICT was,
  including when the domain carve-out overrode the tutorial default)
RATIONALE: 2-3 sentences citing which of the above drove the decision.]"""


def build_eloquence_prompt(transcript: str) -> str:
    """Build the prompt for one post's audio_transcription."""
    return f"""TRANSCRIPT:
{transcript or ''}

{ELOQUENCE_PROMPT}"""


def build_eloquence_batch_request(shortcode: str, transcript: str) -> dict:
    """One /v1/chat/completions batch request line for scripts/score_eloquence.py
    --batch (core/eloquence_batch_processor.py), pinned to "gpt-4.1" to match
    score_and_stamp_eloquence()'s immediate-call model exactly."""
    from core.model_router import get_router

    return get_router().build_batch_chat_request(
        shortcode, build_eloquence_prompt(transcript), model_id="gpt-4.1"
    )


def parse_eloquence(raw: str):
    """Parse the model's raw output into
    (is_eloquent: bool | None, is_tutorial: bool | None, rationale: str).

    is_eloquent is None (with the other fields best-effort/empty) if no
    parseable VERDICT line is found.
    """
    if not raw:
        return None, None, ""

    verdict_match = re.search(r'VERDICT:\s*(YES|NO)', raw, re.IGNORECASE)
    if not verdict_match:
        return None, None, raw.strip()

    is_eloquent = verdict_match.group(1).upper() == "YES"

    tutorial_match = re.search(r'TUTORIAL:\s*(YES|NO)', raw, re.IGNORECASE)
    is_tutorial = (tutorial_match.group(1).upper() == "YES") if tutorial_match else None

    rationale_match = re.search(r'RATIONALE:\s*(.+)', raw, re.IGNORECASE | re.DOTALL)
    rationale = rationale_match.group(1).strip() if rationale_match else ""

    return is_eloquent, is_tutorial, rationale


def score_and_stamp_eloquence(db, shortcode: str, transcript: str):
    """Score one post's transcript and write is_eloquent/is_tutorial/
    eloquence_rationale. Returns is_eloquent (bool) on success, or None if
    the model's output wasn't parseable (nothing is written in that case).

    Does not apply passes_prefilter() itself — callers (scripts/
    score_eloquence.py) decide which posts are worth the LLM call.
    """
    from core.model_router import get_router

    prompt = build_eloquence_prompt(transcript)
    response = get_router()._openai_text("gpt-4.1", prompt)
    is_eloquent, is_tutorial, rationale = parse_eloquence(response) if response else (None, None, "")
    if is_eloquent is None:
        return None

    db.update_eloquence(shortcode, is_eloquent, rationale, is_tutorial=is_tutorial)
    return is_eloquent
