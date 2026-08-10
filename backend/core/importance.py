#!/usr/bin/env python3
"""
Importance scoring for the SuperBrain analysis pipeline.

Lets reels/posts be sorted by how worth-revisiting they actually are, rather
than just by recency or category — a meme is not automatically low value and
a "serious" topic is not automatically high value; see IMPORTANCE_PROMPT.

Same pattern as core/categories.py / core/languages.py: a prompt fragment
(IMPORTANCE_PROMPT) is spliced into main.py's structured summary prompt, and
the model's raw output is parsed back into a validated value with
parse_importance().
"""

import re

# Spliced into generate_final_summary()'s prompt (main.py) as the
# ⭐ IMPORTANCE field, alongside 📂 CATEGORY and 🌐 LANGUAGE.
#
# Calibrated against real saved posts, not written in the abstract — e.g. two
# reels from the same creator on similar self-improvement topics: one that
# names and explains the Pratfall Effect with a concrete mechanism scores far
# higher than one that says "there's a principle for this, follow along to
# learn more" without ever explaining it. Same topic, same creator, very
# different payload — that gap is what this rubric scores on.
IMPORTANCE_PROMPT = """[Rate how much lasting value this content has, 1-5 — value can come from
two different directions, weigh whichever is actually present:
  - Practical: a specific technique, method, fact, tool, or recommendation
    explained clearly enough to apply or look up again.
  - Conceptual: an idea, argument, or framing substantial enough to genuinely
    change how you think about something — a philosophical point, a book's
    core idea, a way of seeing a problem — even with no actionable "method"
    attached.

5 = Either form of value, fully delivered: a technique/method explained well
    enough to actually use, or an idea/argument developed with real
    reasoning behind it (not just stated) — the kind of content worth
    revisiting or sitting with again.
4 = Real value present but partial: a technique mentioned with some of the
    reasoning but not fully explained, a recommendation (book/talk/resource)
    with enough framing to know specifically why it's worth following up on,
    or an idea that's interesting but only partially developed.
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

Output just the number, optionally with a short justification.]"""


def parse_importance(raw: str):
    """Parse a raw IMPORTANCE field into an int 1-5, or None if absent/unparseable.

    Accepts a bare number, or a number followed by justification text (e.g.
    "4 - solid technique but only partially explained").
    """
    if not raw:
        return None
    m = re.search(r'[1-5]', raw)
    return int(m.group(0)) if m else None


# Usernames whose posts the user has manually confirmed are consistently
# worth revisiting, independent of how any single post scores in isolation —
# the per-post rubric above has no memory of past posts from the same
# creator, so this is a deliberate, explicit override rather than something
# asked of the LLM. Keyed lowercase; extend as the user confirms more.
TRUSTED_CREATORS = {
    "erinmerylstudy": "psychology / personal-development / learning creator the user follows and consistently finds useful",
}


def apply_trusted_creator_boost(importance, username: str):
    """Floor (never lower) a trusted creator's score at 4.

    A post that already scored 5 on its own merits stays a 5 — this only
    rescues a trusted creator's post from a low per-post score, it doesn't
    cap or override a genuinely high one. No-op if importance is None (the
    model didn't produce a parseable score) or username isn't trusted.
    """
    if importance is None or not username:
        return importance
    if username.strip().lower() in TRUSTED_CREATORS:
        return max(importance, 4)
    return importance
