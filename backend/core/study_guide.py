"""
On-demand study-guide synthesis for the SuperBrain library.

Turns a user-picked set of posts (a manual selection, a search result, or an
entire theme/cluster from superbrain-web's /space view) into one or more
distilled markdown documents, persisted together as a "collection" (see
core/database.py's study_guide_collections/study_guides tables) — see
superbrain-web's /study-guides for the UI. Unlike importance/eloquence
scoring, this never runs automatically over the whole library; it only runs
when the user explicitly asks for a specific slice.

v1 design note (documented here deliberately, since a follow-up v2 has
already been agreed on with the user): dedup of repeated points across
source posts happens INSIDE the synthesis prompts below — the model is
instructed to merge redundant points itself, both within one call
(build_study_guide_prompt) and across multiple calls (build_merge_prompt,
build_reconcile_prompt). There is no separate claim-extraction step and no
chunk-level embeddings anywhere in this module. That's a deliberate,
cost-conscious choice (the user did not want to pay for a new embedding pass
alongside this), not an oversight. The planned v2 is real semantic dedup via
extracted atomic claims + chunk-level embeddings, clustered the way
core/rag.py's module docstring already flags as missing for chat retrieval
too — see superbrain-web/src/lib/ideas.ts for that v1's matching disclaimer.
Not implemented yet — do not assume it exists.

Multi-call pipeline (generate_study_guide_pipeline, >MAX_STUDY_GUIDE_POSTS):
by explicit user request, an over-cap request runs BOTH a single pass over
every included post at once (role="full" — better at catching connections
that only show up across the whole set, but more prone to losing detail in
a very large prompt) AND a chunked-then-merged pass (chunk_posts() splits
along semantic boundaries when known, role="chunk" + role="merge" — more
thorough per-chunk, but blind to anything that only connects across chunk
boundaries), then reconciles the two into role="final". Every intermediate
guide is persisted, not just the final one — the user explicitly wants to
be able to inspect how the final guide was built, not just trust it.

Every LLM call in this module is pinned to OpenAI's STUDY_GUIDE_MODEL
specifically via ModelRouter.generate_openai_only_text() — no Groq/Gemini/
OpenRouter/Ollama fallback. Also an explicit user request (not a technical
necessity): a partial pipeline should never silently mix model quality
across chunks/full/merge/final.
"""

import math
import re
from datetime import datetime

# Pinned model for this feature specifically — independent of the router's
# usual OPENAI_TEXT_MODEL-driven default (see generate_openai_only_text() in
# core/model_router.py). Change here, not via an env var, if this ever needs
# to move off GPT-5.6 Luna.
STUDY_GUIDE_MODEL = "gpt-5.6-luna"

# GPT-5-family models spend part of max_completion_tokens on invisible
# reasoning before writing anything — a real incident here was a merge call
# (concatenating several already-long chunk guides) whose reasoning alone
# consumed the entire default 4000-token budget, coming back with
# finish_reason "length" and empty content. 25k gives real headroom for
# both reasoning and a long combined answer; applied to every call in this
# pipeline (not just merge/reconcile) since a large chunk/full pass could
# hit the same wall. A generous completion budget needs a correspondingly
# long request timeout, or a legitimately-in-progress call gets cut off
# client-side before it can finish.
STUDY_GUIDE_MAX_COMPLETION_TOKENS = 25000
STUDY_GUIDE_REQUEST_TIMEOUT_S = 300

# Posts scoring below this on the existing 1-5 importance rubric
# (core/importance.py) are dropped before synthesis — low-value content
# (memes, pure personal-branding clips) shouldn't dilute a study guide.
# Unscored posts (importance IS NULL) are kept, not excluded — NULL means
# "never scored", not "scored low". Duplicated (not shared) as a matching
# constant in superbrain-web/src/lib/ideas.ts for the same rule applied to
# tag-frequency counting — Python and the Next.js app can't share a constant
# across that boundary; keep both in sync by hand if this changes.
MIN_STUDY_GUIDE_IMPORTANCE = 3

# Max posts per individual synthesis call (a solo generation, or one chunk
# of the multi-call pipeline) — protects prompt size/cost/quality per call,
# not a hard rejection ceiling on the whole request (see
# generate_study_guide_pipeline(), which chunks anything over this instead
# of rejecting it).
MAX_STUDY_GUIDE_POSTS = 80

# Hard ceiling on a whole request, regardless of chunking — protects against
# an accidental "generate from my entire 2000-post library" click turning
# into dozens of paid calls. Well above any real cluster size seen so far
# (up to ~300), so it should never be hit in normal use.
ABSOLUTE_MAX_STUDY_GUIDE_POSTS = 400

# Per-post character budget for transcript/visual-analysis excerpts fed into
# the prompt — same idea as core/rag.py's MAX_CONTENT_CHARS_PER_POST, kept
# smaller here since a single call can include far more posts (up to
# MAX_STUDY_GUIDE_POSTS) than a chat answer's handful of retrieved sources.
MAX_CONTENT_CHARS_PER_POST = 1200

DEFAULT_TITLE_PREFIX = "Study Guide"


def filter_low_importance(posts: list) -> tuple:
    """Split posts into (included, excluded) by MIN_STUDY_GUIDE_IMPORTANCE.

    excluded only ever contains posts with a real score below the floor —
    never unscored (importance is None) posts.
    """
    included, excluded = [], []
    for post in posts:
        importance = post.get("importance")
        if importance is not None and importance < MIN_STUDY_GUIDE_IMPORTANCE:
            excluded.append(post)
        else:
            included.append(post)
    return included, excluded


def _format_post_for_prompt(post, index):
    parts = [f"[{index}] \"{post.get('title') or 'Untitled'}\" (@{post.get('username', '')})"]
    tags = post.get("tags") or []
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    if post.get("summary"):
        parts.append(f"Summary: {post['summary']}")
    extra = "\n".join(filter(None, [
        post.get("audio_transcription"),
        post.get("visual_analysis"),
        post.get("text_analysis"),
    ]))
    if extra:
        parts.append(f"Details: {extra[:MAX_CONTENT_CHARS_PER_POST]}")
    return "\n".join(parts)


def build_study_guide_prompt(posts: list) -> str:
    """Build the synthesis prompt for one call's worth of already-filtered
    posts (a solo generation, or one leg of the multi-call pipeline).

    Explicitly instructs the model to do the dedup work itself (see the
    module docstring's v1 note) — group into subtopics, merge repeated
    points into one bullet noting how many sources agree, and cite the
    [n] source tags a point drew from.
    """
    context = "\n\n".join(_format_post_for_prompt(p, i + 1) for i, p in enumerate(posts))
    return f"""You are helping the owner of a personal library of saved Instagram reels, YouTube videos, and web pages turn a chosen slice of it into a study guide they can read once and keep, instead of rewatching every source video.

Below are {len(posts)} saved posts, numbered [1] through [{len(posts)}].

{context}

Write a distilled study guide in Markdown:
- Start with a single `# Title` line summarizing the overall topic — this becomes the saved document's title.
- Group the content into a few clear subtopic sections (`##` headings).
- Under each section, write concise bullet points of the actual takeaways — techniques, facts, arguments, recommendations.
- When multiple sources make essentially the same point, merge them into ONE bullet rather than repeating it, and note how many sources agree, e.g. "(mentioned in [2], [5], [9])".
- End every bullet with the [n] source tags it draws from, so the reader can go find the original video if they want more detail.
- Skip filler, generic hooks, and anything with no real content — this is a reference document, not a transcript.
- Do not invent anything not actually present in the posts above.
"""


def build_merge_prompt(chunk_guides: list) -> str:
    """Combine N already-generated chunk study guides (each covering a
    different slice of the same larger selection/cluster) into one
    deduplicated guide.

    Input here is each chunk's finished markdown, not raw post content —
    cheap relative to the per-chunk generation calls, but it also means
    recurrence counts across chunks are approximate: the model can notice
    two chunk guides make the same point, but can't re-tally exact per-post
    citations the way within-chunk dedup can (see the module docstring).
    """
    sections = "\n\n---\n\n".join(
        f'[Guide {i + 1}: "{g["title"]}"]\n{g["content"]}' for i, g in enumerate(chunk_guides)
    )
    return f"""Below are {len(chunk_guides)} study guides, each independently distilled from a different slice of the same larger topic/collection.

{sections}

Combine them into ONE unified study guide in Markdown:
- Start with a single `# Title` line for the combined topic.
- Merge points that appear in multiple guides into one bullet, noting how many of the {len(chunk_guides)} guides made that point (e.g. "(appears in 3 of {len(chunk_guides)} guides)").
- Keep genuinely distinct points from each guide, organized into clear `##` sections.
- Do not just concatenate the guides one after another — actually synthesize them into one coherent document.
"""


def build_reconcile_prompt(full_guide: dict, merged_guide: dict) -> str:
    """Final pass: reconcile the whole-selection pass against the
    chunk-then-merge pass into the single guide the user actually reads
    first (role="final") — see the module docstring for why both exist.
    """
    return f"""Below are two independently-produced study guides covering the exact same set of saved posts, produced two different ways:

[Guide A — generated from every post at once]
{full_guide['content']}

[Guide B — generated by splitting the posts into smaller groups, summarizing each group, then merging those summaries]
{merged_guide['content']}

Produce ONE final, best-of-both study guide in Markdown:
- Start with a single `# Title` line.
- Where both guides agree on a point, keep it once, stated clearly.
- Where one guide has a genuinely useful point the other lacks, include it.
- Resolve any contradictions using your own judgment about which is better supported.
- Organize into clear `##` sections — this is the document the user reads first, so it should read as one coherent guide, not a diff between the two inputs.
"""


def parse_study_guide_title(markdown: str) -> str:
    """Pull the first `# Heading` out of generated markdown for use as the
    saved document's title; falls back to a dated placeholder if the model
    didn't produce one.
    """
    if markdown:
        m = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return f"{DEFAULT_TITLE_PREFIX} — {datetime.utcnow().strftime('%Y-%m-%d')}"


def _even_split(posts: list, max_per_chunk: int) -> list:
    """Split into as-equal-as-possible chunks (e.g. 90 posts -> 45+45, not
    80+10) rather than greedily maxing out each chunk and leaving a small,
    lopsided leftover."""
    if not posts:
        return []
    n_chunks = math.ceil(len(posts) / max_per_chunk)
    chunk_size = math.ceil(len(posts) / n_chunks)
    return [posts[i:i + chunk_size] for i in range(0, len(posts), chunk_size)]


def chunk_posts(posts: list, groups: "list[list[str]] | None" = None, max_per_chunk: int = MAX_STUDY_GUIDE_POSTS) -> list:
    """Split posts into chunks of at most max_per_chunk for the multi-call
    pipeline.

    If `groups` (shortcode lists — e.g. a theme's micro-clusters) is given,
    chunks are packed along those semantic boundaries: consecutive groups
    are combined into one chunk until adding the next would exceed
    max_per_chunk, so each chunk guide stays topically coherent instead of
    being an arbitrary positional slice. Falls back to even positional
    splitting when no groups are known (e.g. a manual selection or search
    result has no cluster structure to pack along).
    """
    by_shortcode = {p["shortcode"]: p for p in posts}

    if groups:
        chunks: list = []
        current: list = []
        for group in groups:
            group_posts = [by_shortcode[sc] for sc in group if sc in by_shortcode]
            if not group_posts:
                continue
            if current and len(current) + len(group_posts) > max_per_chunk:
                chunks.append(current)
                current = []
            current.extend(group_posts)
        if current:
            chunks.append(current)

        # A post not covered by any group (shouldn't normally happen, but
        # groups are caller-supplied) still needs to end up somewhere.
        covered = {p["shortcode"] for chunk in chunks for p in chunk}
        leftover = [p for p in posts if p["shortcode"] not in covered]
        if leftover:
            chunks.extend(_even_split(leftover, max_per_chunk))
        if chunks:
            return chunks

    return _even_split(posts, max_per_chunk)


def expected_guide_count(posts: list, groups: "list[list[str]] | None" = None) -> int:
    """How many guides generate_study_guide_pipeline() will end up producing
    for this request, computed synchronously (no LLM calls) so a caller can
    show real generation progress ("3 of 7") without waiting for the
    pipeline itself to run. Raises ValueError under the same condition
    generate_study_guide_pipeline() would (nothing left after the
    importance filter).
    """
    included, _ = filter_low_importance(posts)
    if not included:
        raise ValueError("Every selected post scored below the importance floor — nothing left to summarize.")
    if len(included) <= MAX_STUDY_GUIDE_POSTS:
        return 1
    return 3 + len(chunk_posts(included, groups=groups))  # final + full + merge + one per chunk


def generate_study_guide_pipeline(router, posts: list, groups: "list[list[str]] | None" = None, on_guide=None) -> list:
    """Full study-guide generation pipeline for a request of any size.

    Returns an ordered list of guide dicts, each
    {role, position, title, content, shortcodes, excluded_shortcodes, model} —
    the same shape api.py persists as study_guides rows (core/database.py).
    `model` is always STUDY_GUIDE_MODEL here (every call in this pipeline is
    pinned to it), stamped per-guide rather than assumed globally so a later
    change to STUDY_GUIDE_MODEL doesn't retroactively misattribute what
    generated an older guide.

    If `on_guide` is given, it's called with each guide dict *as soon as
    that guide is generated* — not batched until the whole pipeline
    finishes. api.py runs this pipeline in a background thread and uses
    on_guide to persist each guide to the database immediately, specifically
    so a crash/restart mid-pipeline only loses whatever guide was actively
    being generated at that instant, not every guide already completed (a
    real gap the user hit: a backend restart mid-way through a 300-post
    generation lost 100% of the already-paid-for work, because nothing was
    written until the very end — see the git history around this function
    for the incident that prompted this).

    At or under MAX_STUDY_GUIDE_POSTS included posts: one call, one guide,
    role="final", position=0.

    Over MAX_STUDY_GUIDE_POSTS: runs BOTH a whole-selection pass and a
    chunked-then-merged pass and reconciles them (see the module docstring
    for why both, not just one). Guides are generated (and emitted to
    on_guide) in dependency/completion order — chunks, then full, then
    merge, then final — NOT position order (final is position 0 but is
    always the last one actually produced, since it depends on full+merge).
    The returned list IS in position order (final, full, merge, chunks...)
    for convenience, but a caller relying on on_guide for incremental
    persistence should not assume anything about final's presence until the
    pipeline actually returns.

    Raises ValueError if every post got filtered out by the importance
    floor (nothing left to synthesize) — callers should turn that into an
    HTTP 400. Raises RuntimeError (via generate_openai_only_text) if OpenAI
    isn't configured or a call fails — no fallback, so this always surfaces
    rather than silently degrading. Guides already emitted via on_guide
    before such a failure are NOT rolled back — they stay persisted (see
    above on why that's the point).
    """
    included, excluded = filter_low_importance(posts)
    if not included:
        raise ValueError("Every selected post scored below the importance floor — nothing left to summarize.")
    excluded_shortcodes = [p["shortcode"] for p in excluded]
    included_shortcodes = [p["shortcode"] for p in included]

    def call(prompt: str) -> str:
        return router.generate_openai_only_text(
            prompt, STUDY_GUIDE_MODEL,
            max_tokens=STUDY_GUIDE_MAX_COMPLETION_TOKENS,
            timeout=STUDY_GUIDE_REQUEST_TIMEOUT_S,
        )

    def emit(guide: dict) -> dict:
        if on_guide:
            on_guide(guide)
        return guide

    if len(included) <= MAX_STUDY_GUIDE_POSTS:
        content = call(build_study_guide_prompt(included))
        guide = {
            "role": "final", "position": 0,
            "title": parse_study_guide_title(content), "content": content,
            "shortcodes": included_shortcodes, "excluded_shortcodes": excluded_shortcodes,
            "model": STUDY_GUIDE_MODEL,
        }
        emit(guide)
        return [guide]

    # --- multi-call pipeline: both a whole-selection pass and a chunked-then-merged pass ---
    chunks = chunk_posts(included, groups=groups)

    chunk_guides = []
    for i, chunk in enumerate(chunks):
        content = call(build_study_guide_prompt(chunk))
        cg = {
            "role": "chunk", "position": 3 + i,
            "title": parse_study_guide_title(content), "content": content,
            "shortcodes": [p["shortcode"] for p in chunk], "excluded_shortcodes": [],
            "model": STUDY_GUIDE_MODEL,
        }
        chunk_guides.append(cg)
        emit(cg)

    full_content = call(build_study_guide_prompt(included))
    full_guide = {
        "role": "full", "position": 1,
        "title": parse_study_guide_title(full_content), "content": full_content,
        "shortcodes": included_shortcodes, "excluded_shortcodes": excluded_shortcodes,
        "model": STUDY_GUIDE_MODEL,
    }
    emit(full_guide)

    merge_content = call(build_merge_prompt(chunk_guides))
    merged_guide = {
        "role": "merge", "position": 2,
        "title": parse_study_guide_title(merge_content), "content": merge_content,
        "shortcodes": included_shortcodes, "excluded_shortcodes": excluded_shortcodes,
        "model": STUDY_GUIDE_MODEL,
    }
    emit(merged_guide)

    final_content = call(build_reconcile_prompt(full_guide, merged_guide))
    final_guide = {
        "role": "final", "position": 0,
        "title": parse_study_guide_title(final_content), "content": final_content,
        "shortcodes": included_shortcodes, "excluded_shortcodes": excluded_shortcodes,
        "model": STUDY_GUIDE_MODEL,
    }
    emit(final_guide)

    return [final_guide, full_guide, merged_guide] + chunk_guides
