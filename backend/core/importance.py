#!/usr/bin/env python3
"""
Importance scoring for the Serendipid analysis pipeline.

Lets reels/posts be sorted by how worth-revisiting they actually are, rather
than just by recency or category — a meme is not automatically low value and
a "serious" topic is not automatically high value; see IMPORTANCE_PROMPT.

Unlike category/language, importance is scored in its own dedicated LLM call
(build_importance_prompt() + ModelRouter.generate_importance_text(), called
from main.py's score_importance()) rather than as one field spliced into the
combined title/summary/tags/... prompt — a single-purpose prompt follows the
rubric more consistently, and generate_importance_text() pins the model to
GPT-5.6 Luna specifically (see IMPORTANCE_MODEL in core/model_router.py)
instead of whatever the latency-ranked router picks.
The model's raw output is a mandatory "<number>: <justification>" line,
parsed back into a validated score with parse_importance() and the
justification text with parse_importance_reason() — both are stored
(analyses.importance / analyses.importance_reason) so a low or surprising
score can be checked against the model's own stated reasoning without
re-running it.
"""

import re

# Sent as part of the prompt built by build_importance_prompt(), called from
# main.py's score_importance() (live pipeline) and scripts/score_importance.py
# (backfill for posts saved before this feature, or before a rubric change).
#
# Calibrated against real saved posts, not written in the abstract — e.g. two
# reels from the same creator on similar self-improvement topics: one that
# names and explains the Pratfall Effect with a concrete mechanism scores far
# higher than one that says "there's a principle for this, follow along to
# learn more" without ever explaining it. Same topic, same creator, very
# different payload — that gap is what this rubric scores on. The
# "charged/serious subject matter" clause below was added after a real
# scoring miss: a meme naming U.S. foreign-policy hypocrisy over a "LOVE"
# halftime show scored a 4 (no explained mechanism, just an irony), while a
# talking-head video explaining the EU's specific "Chat Control" legislative
# mechanism scored only a 3 — backwards, since the second post is the one
# doing real explanatory work.
IMPORTANCE_PROMPT = """[Rate how much lasting value this content has, 1-5 — value can come from
two different directions, weigh whichever is actually present:
  - Practical: a specific technique, method, fact, tool, or recommendation
    explained clearly enough to apply or look up again. "Fact" here means a
    generalizable one — a statistic, a mechanism, a data point useful beyond
    this one story — not an incidental/biographical detail about a specific
    person or event whose only interest is that it happened (see the
    "informational density" trap below).
  - Conceptual: an idea, argument, or framing substantial enough to genuinely
    change how you think about something, OR substantial enough to spark real
    intellectual engagement — a train of thought worth continuing, a question
    worth sitting with or debating — even if it never resolves into a settled
    new opinion. Prompting genuine further thought counts as much as changing
    someone's mind; it doesn't have to end in persuasion to have value — a
    philosophical point, a book's core idea, a way of seeing a problem — even
    with no actionable "method" attached.

5 = Either form of value, fully delivered: a technique/method explained well
    enough to actually use, or an idea/argument developed with real
    reasoning behind it (not just stated) — whether it changes your view or
    hands you a fully-formed train of thought or question substantial
    enough to sit with and argue over — the kind of content worth
    revisiting again.
4 = Real value present but partial: a technique mentioned with some of the
    reasoning but not fully explained, a recommendation (book/talk/resource)
    with enough framing to know specifically why it's worth following up on,
    an idea that's interesting but only partially developed, or a genuine
    question/reframe raised with enough framing to see why it matters but
    without the reasoning fully worked through.
3 = A claim, concept, or theme is named or gestured at with little
    development — mildly interesting in the moment, but nothing you'd come
    back to; a teaser rather than a payload.
2 = Personal narrative, reaction, opinion, or mood content, with at most
    incidental food for thought.
1 = No extractable or plausible value — pure self-introduction, personal
    branding, showing off a possession/lifestyle with no reasoning behind
    the preference, or a joke/trend with nothing beneath the format and
    nothing reasonably inferable either.

Judge strictly by what's actually delivered or reasonably inferable — not by
subject matter, and not by format:
- Topic is not a proxy for value: an "impressive"-sounding topic that only
  shows off or namedrops scores low; an "ordinary" topic that's actually
  explained or reasoned through scores high. E.g. "here's my favorite lens"
  with no explanation of why is low value; a reel breaking down a
  composition technique is high value, on the same general subject.
- Format is not a proxy for value either: a meme or joke is not
  automatically low score. If a genuine insight, fact, or observation could
  reasonably be extracted or extrapolated from its premise — even if the
  reel itself never states it outright — score it on that content. Only
  score a meme/joke at 1 if nothing of substance can plausibly be drawn from
  it even on reflection.
- Charged or "serious" subject matter (politics, injustice, world events) is
  the topic-is-not-a-proxy trap in its most common disguise: naming an
  emotionally loaded concept — hypocrisy, corruption, oppression, "soft
  power" — is not the same as explaining it. A post that only points at the
  irony/injustice without showing the mechanism behind it is a 2-3 at most,
  no matter how weighty the subject sounds. Do not let vocabulary like
  "hypocrisy," "systemic," or charged political language signal depth by
  itself — check whether the post actually shows HOW or WHY, or just names
  the feeling.
  Worked contrast: a meme captioned "they preach peace on TV while doing X"
  names a real irony but explains no mechanism for why X happens or how the
  two connect beyond juxtaposition — 2-3, even though the topic is serious.
  A separate post that explains the specific mechanism by which a law or
  policy achieves its effect — e.g. "the rule requires an absolute majority
  to reject it, so abstentions function as a yes vote" or "it scans content
  before encryption rather than after, which is legally how it avoids the
  ban on reading encrypted messages" — is doing real explanatory work and
  should score 4-5, even delivered as a casual talking-head video rather
  than a formal analysis. For THIS specific trap — a claim wrapped in
  emotionally loaded language — the deciding factor is whether a mechanism/
  reasoning chain is present, not the vocabulary or delivery format. This is
  a check on that one failure mode, not a rule for the rubric as a whole:
  plenty of high-value content earns a high score without walking through a
  mechanism — a clearly stated important fact or recommendation (see
  Practical above), or a short but genuinely thought-provoking reframe that
  sparks a real train of thought (see Conceptual above) — so don't apply
  "no mechanism = low score" outside of the charged-vocabulary case this
  paragraph is about.
- Informational density is not a proxy for value either: a post can be
  packed with concrete, verifiable specifics — names, dollar figures, dates,
  precise numbers — and still be a 2-3 if those specifics don't generalize
  beyond the one story they're reporting. A fact only counts as Practical
  value (see definition above) if it's something worth referencing again for
  a reason beyond curiosity about that particular person or event.
  Worked contrast: a post reporting "X is set to inherit $100M from Y, is
  37, and was never interviewed by investigators" is specific and
  verifiable, but has no further utility once read — it's a teaser for a
  fuller (often paywalled) story, tier 3 at most, even though it's dense
  with detail. A post citing a statistic that reveals a real pattern (a
  rate, a trend), or explaining a mechanism using specific numbers, is doing
  something different — the numbers are in service of a reusable insight,
  not just reporting on one situation — and should be scored on that
  insight per the criteria above.

Output in exactly this format, on one line: a single digit 1-5, then a
colon, then a short justification (1-2 sentences) explaining why this
specific score applies — e.g. "4: Names a specific negotiating tactic and
explains why it works, but doesn't walk through the full mechanism." The
justification is required, not optional — never output the number alone.]"""


def build_importance_prompt(title: str, summary: str, tags, category) -> str:
    """Build the minimal prompt used to score one post's importance — shared
    by main.py's live pipeline and scripts/score_importance.py's backfill so
    both ask the model the exact same thing.
    """
    tags_str = ', '.join(tags) if tags else ''
    category_str = ', '.join(category) if category else ''
    return f"""TITLE: {title or ''}

SUMMARY: {summary or ''}

TAGS: {tags_str}

CATEGORY: {category_str}

{IMPORTANCE_PROMPT}"""


def parse_importance(raw: str):
    """Parse a raw IMPORTANCE field into an int 1-5, or None if absent/unparseable.

    Accepts a bare number, or (the now-mandatory format, see IMPORTANCE_PROMPT)
    a number followed by ": <justification>" (e.g.
    "4: solid technique but only partially explained").
    """
    if not raw:
        return None
    m = re.search(r'[1-5]', raw)
    return int(m.group(0)) if m else None


def parse_importance_reason(raw: str):
    """Parse the justification text that follows the leading 1-5 digit, or
    None if there's no score to anchor on or nothing follows it.

    Expects IMPORTANCE_PROMPT's mandated "<number>: <justification>" format
    but tolerates a missing/different separator by taking whatever text
    follows the first digit, stripped of leading punctuation/whitespace.
    """
    if not raw:
        return None
    m = re.search(r'[1-5]', raw)
    if not m:
        return None
    reason = raw[m.end():].strip().lstrip(':-–—.,) ').strip()
    return reason or None


# Usernames whose posts are consistently worth revisiting, independent of how
# any single post scores in isolation — the per-post rubric above has no
# memory of past posts from the same creator, so this is a deliberate,
# explicit override rather than something asked of the LLM. Configured as
# trusted_creators ({username: reason}) in config/user_config.json
# (core/app_config.py).


def apply_trusted_creator_boost(importance, username: str, reason: str = None):
    """Floor (never lower) a trusted creator's score at 4.

    A post that already scored 5 on its own merits stays a 5 — this only
    rescues a trusted creator's post from a low per-post score, it doesn't
    cap or override a genuinely high one. No-op if importance is None (the
    model didn't produce a parseable score) or username isn't trusted.

    Returns (importance, reason). When the floor actually changes the score,
    a note is appended to `reason` — otherwise the stored justification
    would describe a score the post no longer has.
    """
    if importance is None or not username:
        return importance, reason
    from core import app_config

    trusted = app_config.trusted_creators()
    key = username.strip().lower()
    if key in trusted:
        boosted = max(importance, 4)
        if boosted != importance:
            note = f"Floored to {boosted}/5 — trusted creator ({trusted[key]})."
            reason = f"{reason} {note}".strip() if reason else note
        return boosted, reason
    return importance, reason


def score_and_stamp_importance(db, shortcode: str, title: str, summary: str, tags, category, username: str):
    """Score one post's importance from its already-stored fields (no
    re-download) and stamp it to CURRENT_ANALYSIS_VERSION on success.

    Extracted from scripts/score_importance.py's per-post loop so the
    backfill script and the API's bulk-rescan endpoint (which uses this as
    the cheap fix for posts stamped exactly version 7 — the only version
    whose gap to current is purely the importance-scoring rubric change)
    share one implementation instead of duplicating the prompt/parse/boost/
    save sequence.

    Returns the final 1-5 score on success, or None if the model didn't
    return a parseable score (nothing is written to the DB in that case).
    """
    from core.model_router import get_router

    prompt = build_importance_prompt(title, summary, tags, category)
    response = get_router().generate_importance_text(prompt)
    importance = parse_importance(response) if response else None
    if importance is None:
        return None

    reason = parse_importance_reason(response)
    importance, reason = apply_trusted_creator_boost(importance, username, reason)
    if not db.update_importance(shortcode, importance, reason):
        return None
    return importance
