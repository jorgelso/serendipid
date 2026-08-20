import type { ChangelogResponse, ClientPost, Collection, Post, SearchSemanticHit } from "@/types/domain";

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

/** media_urls come back as relative paths ("/media/{shortcode}/video.mp4")
 * — the /media mount has no auth dependency (same as /static), so prefixing
 * with the backend's base URL is all a browser needs to fetch/play them
 * directly. */
export function resolveMediaUrls(mediaUrls: string[], apiBaseUrl: string): string[] {
  return mediaUrls.map((u) => (u.startsWith("/media/") ? `${apiBaseUrl}${u}` : u));
}

/** Strips the embedding and resolves the thumbnail + media URLs to absolute
 * URLs in one step — the shape every post should be in by the time it
 * reaches a client component. */
export function toDisplayPost(post: Post, apiBaseUrl: string): ClientPost {
  const client = toClientPost(post);
  return {
    ...client,
    thumbnail: resolveThumbnailUrl(client.thumbnail, apiBaseUrl),
    media_urls: resolveMediaUrls(client.media_urls, apiBaseUrl),
  };
}

/** Most-recently-analyzed first — the ordering behind the Home/Browse feeds. */
export function sortPostsByRecency(posts: Post[]): Post[] {
  return [...posts].sort((a, b) => {
    const aTime = a.analyzed_at ? Date.parse(a.analyzed_at) : 0;
    const bTime = b.analyzed_at ? Date.parse(b.analyzed_at) : 0;
    return bTime - aTime;
  });
}

/** Highest importance (1-5) first — unscored posts (null) sink to the
 * bottom rather than being treated as 0, since "not scored yet" isn't the
 * same claim as "scored low". Recency breaks ties, including among the
 * unscored group. */
export function sortPostsByImportance(posts: Post[]): Post[] {
  return sortPostsByRecency(posts).sort((a, b) => {
    if (a.importance == null && b.importance == null) return 0;
    if (a.importance == null) return 1;
    if (b.importance == null) return -1;
    return b.importance - a.importance;
  });
}

/** Shared by /api/feed and the Browse page's initial server render, so both
 * apply category/collection filtering and sorting identically. */
export function filterPosts(
  posts: Post[],
  collections: Collection[],
  options: {
    // A post's categories must all be within this set ("exact"/subset match,
    // the default) — or just overlap it at all ("any"/union match) when
    // categoryMatch is explicitly "any". Subset match is what keeps a
    // "Books"-only browse from pulling in a post also tagged Humor & Memes;
    // "any" exists as an explicit broaden-out escape hatch for when subset
    // match returns too little (see the Browse page's fallback hint).
    category?: string[];
    categoryMatch?: "exact" | "any";
    language?: string;
    collectionId?: string;
    sort?: "recent" | "importance";
    // Toggle set, not a single value — e.g. [1, 3] keeps posts scored either
    // 1 or 3. Empty/undefined means no importance filtering at all.
    importance?: number[];
    // Eloquence view (see /eloquent page): eloquent=true keeps only
    // is_eloquent===1; tutorial narrows further to is_tutorial===1 ("yes")
    // or ===0 ("no") among those — undefined/"all" applies no narrowing.
    eloquent?: boolean;
    tutorial?: "yes" | "no";
  }
): Post[] {
  let filtered = options.sort === "importance" ? sortPostsByImportance(posts) : sortPostsByRecency(posts);
  if (options.category && options.category.length > 0) {
    const selected = new Set(options.category);
    filtered =
      options.categoryMatch === "any"
        ? filtered.filter((p) => p.category.some((c) => selected.has(c)))
        : filtered.filter((p) => p.category.length > 0 && p.category.every((c) => selected.has(c)));
  }
  if (options.language) {
    filtered = filtered.filter((p) => p.language.includes(options.language!));
  }
  if (options.collectionId) {
    const collection = collections.find((c) => c.id === options.collectionId);
    const idSet = new Set(collection?.post_ids ?? []);
    filtered = filtered.filter((p) => idSet.has(p.shortcode));
  }
  if (options.importance && options.importance.length > 0) {
    const importanceSet = new Set(options.importance);
    filtered = filtered.filter((p) => p.importance != null && importanceSet.has(p.importance));
  }
  if (options.eloquent) {
    filtered = filtered.filter((p) => p.is_eloquent === 1);
  }
  if (options.tutorial === "yes") {
    filtered = filtered.filter((p) => p.is_tutorial === 1);
  } else if (options.tutorial === "no") {
    filtered = filtered.filter((p) => p.is_tutorial === 0);
  }
  return filtered;
}

export interface VersionFilters {
  category: string;
  language: string;
  sort: "recent" | "importance";
}

export interface VersionSummary {
  version: number;
  count: number;
  isCurrent: boolean;
  changelogTitle: string | null;
  changelogDescription: string | null;
  // Every shortcode at this version, not just what's currently paginated in
  // — "Rescan entire version" needs to target the whole cohort.
  shortcodes: string[];
}

/** Groups posts by analysis_version, sorted oldest-first — unrelated to
 * "collections" (a separate, user-curated Instagram-folder concept; see
 * Collection). Only versions with at least one current post are included. */
export function versionSummaries(posts: Post[], changelog: ChangelogResponse | null): VersionSummary[] {
  const byVersion = new Map<number, Post[]>();
  for (const post of posts) {
    const group = byVersion.get(post.analysis_version);
    if (group) {
      group.push(post);
    } else {
      byVersion.set(post.analysis_version, [post]);
    }
  }

  const currentVersion = changelog?.current_version ?? null;
  const historyByVersion = new Map((changelog?.history ?? []).map((h) => [h.version, h]));

  return Array.from(byVersion.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([version, group]) => ({
      version,
      count: group.length,
      isCurrent: version === currentVersion,
      changelogTitle: historyByVersion.get(version)?.title ?? null,
      changelogDescription: historyByVersion.get(version)?.description ?? null,
      shortcodes: group.map((p) => p.shortcode),
    }));
}

/** Scopes filterPosts to a single analysis_version. No collectionId option —
 * collections are orthogonal to version cohorts, not a valid filter here. */
export function filterVersionPosts(
  posts: Post[],
  version: number,
  options: { category?: string; language?: string; sort?: "recent" | "importance" }
): Post[] {
  return filterPosts(
    posts.filter((p) => p.analysis_version === version),
    [],
    // categoryMatch "any": version filtering is a single-select, unrelated
    // to Browse's exact/subset matching — keep its original "contains this
    // category" behavior unchanged.
    { ...options, category: options.category ? [options.category] : undefined, categoryMatch: "any" }
  );
}

/** A post can carry 1-3 categories now — options are every distinct label
 * seen across the library, not one-per-post. */
export function categoryOptions(posts: Post[]): string[] {
  const set = new Set<string>();
  for (const post of posts) {
    for (const category of post.category) set.add(category);
  }
  return Array.from(set).sort();
}

/** A post can carry one or two languages — options are every distinct label
 * seen across the library. */
export function languageOptions(posts: Post[]): string[] {
  const set = new Set<string>();
  for (const post of posts) {
    for (const language of post.language) set.add(language);
  }
  return Array.from(set).sort();
}

/** Each of a post's categories counts independently (a post with 2 labels
 * contributes to 2 bars) — the natural reading for a multi-label taxonomy. */
export function computeCategoryCounts(posts: Post[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const post of posts) {
    const labels = post.category.length > 0 ? post.category : ["uncategorized"];
    for (const label of labels) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
}

/** categoryOptions(posts) only surfaces labels that already appear on some
 * post — a canonical category with 0 current posts (e.g. one added by a
 * later pipeline version, before which nothing could have been tagged with
 * it) is otherwise invisible in the filter dropdown. Union with the full
 * canonical list (backend GET /categories' `canonical` field) so every
 * category is always selectable. */
export function unionWithCanonicalCategories(posts: Post[], canonical: string[]): string[] {
  return Array.from(new Set([...canonical, ...categoryOptions(posts)])).sort();
}

/** Same fix as unionWithCanonicalCategories, for Insights' category
 * breakdown — every canonical label starts at 0 instead of being omitted
 * entirely when no post currently carries it. */
export function computeCategoryCountsWithCanonical(posts: Post[], canonical: string[]): [string, number][] {
  const counts = new Map<string, number>(canonical.map((c) => [c, 0]));
  for (const post of posts) {
    const labels = post.category.length > 0 ? post.category : ["uncategorized"];
    for (const label of labels) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
}

export function computeLanguageCounts(posts: Post[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const post of posts) {
    const labels = post.language.length > 0 ? post.language : ["unknown"];
    for (const label of labels) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
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
 * until a category is actually expanded (see LazyPostList). A post with
 * multiple categories appears once under each — expected for a multi-label
 * taxonomy, not a bug. */
export function groupShortcodesByCategory(
  posts: { shortcode: string; category: string[] }[]
): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const post of posts) {
    const labels = post.category.length > 0 ? post.category : ["uncategorized"];
    for (const label of labels) {
      (groups[label] ??= []).push(post.shortcode);
    }
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
          importance: null,
          thumbnail: hit.thumbnail,
          title: hit.title,
          summary: hit.summary,
          caption: null,
          tags: hit.tags,
          music: null,
          category: hit.category,
          language: [],
          visual_analysis: null,
          audio_transcription: null,
          text_analysis: null,
          is_hidden: 0,
          source_hashtags: [],
          analysis_version: 0,
          needs_review: false,
          media_files: [],
          media_urls: [],
          enjoyment_rating: null,
          perceived_importance_rating: null,
          is_eloquent: null,
          is_tutorial: null,
          eloquence_rationale: null,
        };

    return {
      ...base,
      title: hit.title ?? base.title,
      summary: hit.summary ?? base.summary,
      tags: hit.tags ?? base.tags,
      category: hit.category ?? base.category,
      thumbnail: resolveThumbnailUrl(hit.thumbnail ?? base.thumbnail, apiBaseUrl),
      media_urls: resolveMediaUrls(base.media_urls, apiBaseUrl),
      similarity: hit.similarity,
    };
  });
}
