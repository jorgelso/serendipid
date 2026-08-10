"""
Retrieval-augmented generation for the RAG chatbot.

Reuses the same per-post embeddings (title+summary+tags) and cosine-ranking
approach as GET /search/semantic (api.py), then hydrates matches with each
post's full stored content and asks the "chat" task's LLM (see
core/model_router.py's generate_chat_text — Gemini -> OpenAI[dedicated
OPENAI_CHAT_API_KEY] -> local Ollama) to answer from it.

Note: retrieval is still only as good as the embedding it's built on, which
covers title+summary+tags, not the full audio_transcription/visual_analysis/
text_analysis blobs — very specific details buried deep in a video may not
surface a post as a match at all. This module compensates a little by
including that full content for whatever *does* match, but can't retrieve a
post the embedding itself missed. (Passage/chunk-level embeddings would fix
this but aren't implemented — see the frontend's chat disclaimer.)
"""

import numpy as np

# Cap how much raw per-post content goes into the prompt so a handful of
# long transcripts/visual analyses don't blow past the model's context
# window or the request timeout.
MAX_CONTENT_CHARS_PER_POST = 2000
MAX_HISTORY_MESSAGES = 8


def rank_by_embedding(query_embedding, stored, limit=20, min_similarity=0.0):
    """
    Rank stored embedding rows against a query embedding by cosine similarity.

    stored: rows from Database.get_all_embeddings() — each a dict with
    "shortcode" and "embedding" (list of floats).

    Returns a list of (similarity, shortcode) tuples, best first. Shared by
    GET /search/semantic and the chat retrieval below so the ranking logic
    only lives in one place.
    """
    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)

    scored = []
    for row in stored:
        vec = np.array(row["embedding"], dtype=np.float32)
        denom = query_norm * np.linalg.norm(vec)
        similarity = float(np.dot(query_vec, vec) / denom) if denom else 0.0
        if similarity >= min_similarity:
            scored.append((similarity, row["shortcode"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def retrieve_relevant_posts(router, db, query, limit=8, min_similarity=0.2):
    """
    Embed `query` and return the top matching posts, hydrated with their
    full stored content (summary + audio_transcription + visual_analysis +
    text_analysis), not just the embedded title/summary/tags snippet.

    Returns [] if no embedding could be generated (e.g. OPENAI_API_KEY not
    configured) or nothing matched above min_similarity.
    """
    query_embedding = router.generate_embedding(query)
    if not query_embedding:
        return []

    stored = db.get_all_embeddings()
    if not stored:
        return []

    ranked = rank_by_embedding(query_embedding, stored, limit=limit, min_similarity=min_similarity)

    results = []
    for similarity, shortcode in ranked:
        post = db.check_cache(shortcode)
        if not post:
            continue
        results.append({
            "shortcode": shortcode,
            "similarity": round(similarity, 4),
            "url": post.get("url", ""),
            "username": post.get("username", ""),
            "title": post.get("title", ""),
            "summary": post.get("summary", ""),
            "tags": post.get("tags", []),
            "category": post.get("category", ""),
            "thumbnail": post.get("thumbnail", ""),
            "audio_transcription": post.get("audio_transcription") or "",
            "visual_analysis": post.get("visual_analysis") or "",
            "text_analysis": post.get("text_analysis") or "",
        })
    return results


def _format_post_for_prompt(post, index):
    parts = [f"[{index}] \"{post['title'] or 'Untitled'}\" (@{post['username']}, {post['url']})"]
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


def build_chat_prompt(question, history, sources):
    """
    Build the prompt sent to the chat LLM: instructions, the retrieved post
    content, recent conversation history, and the new question.
    """
    if sources:
        context = "\n\n".join(
            _format_post_for_prompt(post, i + 1) for i, post in enumerate(sources)
        )
    else:
        context = "(No saved posts matched this question closely enough.)"

    history_lines = []
    for msg in history[-MAX_HISTORY_MESSAGES:]:
        speaker = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{speaker}: {msg['content']}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior messages)"

    return f"""You are a helpful assistant answering questions about a personal library of saved Instagram reels, YouTube videos, and web pages.

Answer ONLY using the saved post content given below. If the answer isn't in there, say you don't have anything saved on that topic — do not make things up. When you draw on a specific post, refer to it by its title and/or its [number] tag so the reader knows which source you mean. If the user asks for sources, links, or "the reels/videos", list the relevant post titles with their [number] tags — the actual clickable cards are rendered separately by the app, so you don't need to write out URLs yourself.

Saved posts that matched this question:
{context}

Recent conversation:
{history_block}

User's new question: {question}

Answer:"""


def _light_source(post):
    """Strip a retrieved post down to what a citation card needs — the full
    audio_transcription/visual_analysis/text_analysis blobs are only needed
    for prompt-building, not for storage in chat_messages.sources or the API
    response (same idea as ClientPost stripping `embedding` on the frontend).

    Deliberately excludes `thumbnail`: it's frequently a full base64 data URI
    (same as the `analyses` table's stored format), and embedding that in
    every chat message would bloat both the API response and the permanent
    chat_messages row for every answer ever given. The frontend already has
    a proxy for exactly this (/api/thumbnail/{shortcode}, built for the same
    reason on the /space view) that resolves it from `shortcode` on demand
    instead — same-origin lookup, nothing to duplicate here.
    """
    return {
        "shortcode": post["shortcode"],
        "similarity": post["similarity"],
        "url": post["url"],
        "username": post["username"],
        "title": post["title"],
        "summary": post["summary"],
        "tags": post["tags"],
        "category": post["category"],
    }


def answer_question(router, db, thread_id, question, limit=8, min_similarity=0.2):
    """
    Retrieve relevant posts for `question`, build a prompt with thread
    history, and generate an answer via the chat-task LLM.

    Synchronous (like generate_embedding/generate_chat_text) — callers in
    api.py should run this via asyncio.to_thread.

    Returns (answer_text: str, sources: list[dict]) — sources are the light
    citation shape (see _light_source), not the full prompt content.
    """
    history = db.get_chat_messages(thread_id)
    sources = retrieve_relevant_posts(router, db, question, limit=limit, min_similarity=min_similarity)
    prompt = build_chat_prompt(question, history, sources)
    answer = router.generate_chat_text(prompt)
    return answer, [_light_source(s) for s in sources]
