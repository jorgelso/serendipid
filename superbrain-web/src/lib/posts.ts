import type { ClientPost, Collection, Post, SearchSemanticHit } from "@/types/domain";

/** Thumbnails may be a full external URL, a data: URI, or a relative
 * /static/... path needing the backend's base URL prefixed (backend/api.py's
 * /static mount has no auth dependency, so the resolved URL works directly
 * in a plain <img> tag). */
export function resolveThumbnailUrl(
  thumbnail: string | null | undefined,
  apiBaseUrl: string
): string | null {
  if (!thumbnail) return null;
  if (thumbnail.startsWith("http://") || thumbnail.startsWith("https://") || thumbnail.startsWith("data:image/")) {
    return thumbnail;
  }
  if (thumbnail.startsWith("/static/")) {
    return `${apiBaseUrl}${thumbnail}`;
  }
  return null;
}

/** Strips the raw embedding field before a post is ever handed to a client
 * component or serialized in an API response. */
export function toClientPost(post: Post): ClientPost {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { embedding, ...rest } = post;
  return rest;
}

/** Strips the embedding and resolves the thumbnail to an absolute URL in one
 * step — the shape every post should be in by the time it reaches a client
 * component. */
export function toDisplayPost(post: Post, apiBaseUrl: string): ClientPost {
  const client = toClientPost(post);
  return { ...client, thumbnail: resolveThumbnailUrl(client.thumbnail, apiBaseUrl) };
}

/** Most-recently-analyzed first — the ordering behind the Home/Browse feeds. */
export function sortPostsByRecency(posts: Post[]): Post[] {
  return [...posts].sort((a, b) => {
    const aTime = a.analyzed_at ? Date.parse(a.analyzed_at) : 0;
    const bTime = b.analyzed_at ? Date.parse(b.analyzed_at) : 0;
    return bTime - aTime;
  });
}

/** Shared by /api/feed and the Browse page's initial server render, so both
 * apply category/collection filtering identically. */
export function filterPosts(
  posts: Post[],
  collections: Collection[],
  options: { category?: string; collectionId?: string }
): Post[] {
  let filtered = sortPostsByRecency(posts);
  if (options.category) {
    filtered = filtered.filter((p) => p.category === options.category);
  }
  if (options.collectionId) {
    const collection = collections.find((c) => c.id === options.collectionId);
    const idSet = new Set(collection?.post_ids ?? []);
    filtered = filtered.filter((p) => idSet.has(p.shortcode));
  }
  return filtered;
}

export function categoryOptions(posts: Post[]): string[] {
  const set = new Set<string>();
  for (const post of posts) {
    if (post.category) set.add(post.category);
  }
  return Array.from(set).sort();
}

export function computeCategoryCounts(posts: Post[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const post of posts) {
    const key = post.category || "uncategorized";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
}

export function computeTagCounts(posts: Post[], limit = 20): [string, number][] {
  const counts = new Map<string, number>();
  for (const post of posts) {
    for (const tag of post.tags ?? []) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

/** Groups shortcodes by category without materializing full post objects —
 * used for the initial page render so large fields (thumbnails) never load
 * until a category is actually expanded (see LazyPostList). */
export function groupShortcodesByCategory(
  posts: { shortcode: string; category: string | null }[]
): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const post of posts) {
    const key = post.category || "uncategorized";
    (groups[key] ??= []).push(post.shortcode);
  }
  return groups;
}

/** Ports pages/2_Search.py's merge: the semantic-search response omits fields
 * like visual_analysis/audio_transcription/text_analysis/likes/post_date, so
 * fill those in from the fuller cached export record by shortcode. */
export function mergeSearchHitsWithPosts(
  hits: SearchSemanticHit[],
  posts: Post[],
  apiBaseUrl: string
): (ClientPost & { similarity: number })[] {
  const byShortcode = new Map(posts.map((p) => [p.shortcode, p]));

  return hits.map((hit) => {
    const full = byShortcode.get(hit.shortcode);
    const base: ClientPost = full
      ? toClientPost(full)
      : {
          shortcode: hit.shortcode,
          url: hit.url,
          username: hit.username,
          content_type: "instagram",
          analyzed_at: null,
          updated_at: null,
          post_date: null,
          likes: null,
          thumbnail: hit.thumbnail,
          title: hit.title,
          summary: hit.summary,
          tags: hit.tags,
          music: null,
          category: hit.category,
          visual_analysis: null,
          audio_transcription: null,
          text_analysis: null,
          is_hidden: 0,
          source_hashtags: [],
        };

    return {
      ...base,
      title: hit.title ?? base.title,
      summary: hit.summary ?? base.summary,
      tags: hit.tags ?? base.tags,
      category: hit.category ?? base.category,
      thumbnail: resolveThumbnailUrl(hit.thumbnail ?? base.thumbnail, apiBaseUrl),
      similarity: hit.similarity,
    };
  });
}
