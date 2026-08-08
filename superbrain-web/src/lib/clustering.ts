// Two-pass hierarchical clustering over stored post embeddings.
//
// Pass 1 (fine): connect posts whose embeddings are highly similar into tight
// micro-clusters (e.g. "guitar tutorials").
// Pass 2 (coarse): cluster the micro-clusters' centroids at a lower threshold,
// merging related micro-clusters into broader themes (e.g. guitar + violin +
// piano micro-clusters -> "Musical instruments").
//
// Pure functions, no I/O — computeThemes() is the entrypoint used by cache.ts.

import type { MicroCluster, Post, Theme } from "@/types/domain";

export interface EmbeddedPost {
  index: number;
  shortcode: string;
  vector: Float32Array; // pre-normalized
}

export function parseEmbedding(raw: string | null): Float32Array | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    const out = new Float32Array(parsed.length);
    for (let i = 0; i < parsed.length; i++) {
      const n = Number(parsed[i]);
      if (!Number.isFinite(n)) return null;
      out[i] = n;
    }
    return out;
  } catch {
    return null;
  }
}

export function normalize(v: Float32Array): Float32Array {
  let sumSq = 0;
  for (let i = 0; i < v.length; i++) sumSq += v[i] * v[i];
  const norm = Math.sqrt(sumSq);
  if (norm === 0) return v;
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i++) out[i] = v[i] / norm;
  return out;
}

export function dot(a: Float32Array, b: Float32Array): number {
  const len = Math.min(a.length, b.length);
  let sum = 0;
  for (let i = 0; i < len; i++) sum += a[i] * b[i];
  return sum;
}

export function createUnionFind(n: number) {
  const parent = new Int32Array(n);
  const rank = new Uint8Array(n);
  for (let i = 0; i < n; i++) parent[i] = i;

  function find(x: number): number {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]]; // path halving
      x = parent[x];
    }
    return x;
  }

  function union(a: number, b: number): void {
    const ra = find(a);
    const rb = find(b);
    if (ra === rb) return;
    if (rank[ra] < rank[rb]) parent[ra] = rb;
    else if (rank[ra] > rank[rb]) parent[rb] = ra;
    else {
      parent[rb] = ra;
      rank[ra]++;
    }
  }

  return { find, union };
}

/** Vectors must already be normalized — similarity is a plain dot product. */
export function connectedComponents(vectors: Float32Array[], threshold: number): number[][] {
  const n = vectors.length;
  const uf = createUnionFind(n);
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (dot(vectors[i], vectors[j]) >= threshold) {
        uf.union(i, j);
      }
    }
  }
  const groups = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const root = uf.find(i);
    const group = groups.get(root);
    if (group) group.push(i);
    else groups.set(root, [i]);
  }
  return Array.from(groups.values());
}

export function centroid(vectors: Float32Array[]): Float32Array {
  const dim = vectors[0].length;
  const sum = new Float32Array(dim);
  for (const v of vectors) {
    for (let i = 0; i < dim; i++) sum[i] += v[i];
  }
  for (let i = 0; i < dim; i++) sum[i] /= vectors.length;
  return normalize(sum);
}

interface PostLike {
  tags: string[];
  category: string | null;
}

// Boilerplate hashtags that show up on almost every Instagram reel regardless
// of topic (platform/format noise, not content signal) — excluded from
// labeling only, not from clustering itself (that's driven by embeddings).
const GENERIC_TAGS = new Set([
  "instagramreel",
  "instagramreels",
  "reel",
  "reels",
  "socialmedia",
  "viral",
  "viralreels",
  "trending",
  "trendingreels",
  "fyp",
  "foryou",
  "foryoupage",
  "explore",
  "explorepage",
  "video",
  "instagram",
  "instagood",
  "contentcreator",
  "follow",
  "share",
  "like",
]);

function normalizeTag(tag: string): string {
  return tag.trim().replace(/^#/, "").toLowerCase();
}

/** Labels a group of posts by its most common tag (falls back to category
 * when tags are too sparse to be meaningful) — no LLM calls. */
export function labelFromPosts(posts: PostLike[]): { label: string; subLabels: string[] } {
  const tagFreq = new Map<string, { count: number; original: string }>();
  for (const post of posts) {
    for (const rawTag of post.tags ?? []) {
      const trimmed = rawTag.trim();
      if (!trimmed || GENERIC_TAGS.has(normalizeTag(trimmed))) continue;
      const key = trimmed.toLowerCase();
      const entry = tagFreq.get(key);
      if (entry) entry.count++;
      else tagFreq.set(key, { count: 1, original: trimmed });
    }
  }

  if (tagFreq.size >= 2) {
    const sorted = Array.from(tagFreq.values()).sort((a, b) => b.count - a.count);
    const [top, ...rest] = sorted;
    return { label: top.original, subLabels: rest.slice(0, 4).map((r) => r.original) };
  }

  const categoryFreq = new Map<string, number>();
  for (const post of posts) {
    if (!post.category) continue;
    categoryFreq.set(post.category, (categoryFreq.get(post.category) ?? 0) + 1);
  }
  if (categoryFreq.size > 0) {
    const [topCategory] = Array.from(categoryFreq.entries()).sort((a, b) => b[1] - a[1])[0];
    return { label: topCategory, subLabels: [] };
  }

  if (tagFreq.size === 1) {
    const [only] = Array.from(tagFreq.values());
    return { label: only.original, subLabels: [] };
  }

  return { label: "Untitled group", subLabels: [] };
}

export interface ClusteringOptions {
  fineThreshold?: number;
  coarseThreshold?: number;
  minThemeSize?: number;
}

const DEFAULT_OPTIONS: Required<ClusteringOptions> = {
  fineThreshold: 0.72,
  coarseThreshold: 0.7,
  minThemeSize: 3,
};

function buildMicroClusters(
  embeddedPosts: EmbeddedPost[],
  postsByShortcode: Map<string, PostLike>,
  fineThreshold: number
): { microClusters: MicroCluster[]; centroids: Float32Array[] } {
  const vectors = embeddedPosts.map((p) => p.vector);
  const groups = connectedComponents(vectors, fineThreshold);

  const microClusters: MicroCluster[] = [];
  const centroids: Float32Array[] = [];

  groups.forEach((indices, i) => {
    const shortcodes = indices.map((idx) => embeddedPosts[idx].shortcode);
    const groupPosts = shortcodes
      .map((sc) => postsByShortcode.get(sc))
      .filter((p): p is PostLike => Boolean(p));
    const { label, subLabels } = labelFromPosts(groupPosts);
    microClusters.push({ id: `micro-${i}`, label, subLabels, postShortcodes: shortcodes });
    centroids.push(centroid(indices.map((idx) => vectors[idx])));
  });

  return { microClusters, centroids };
}

function buildThemes(
  microClusters: MicroCluster[],
  centroids: Float32Array[],
  coarseThreshold: number,
  postsByShortcode: Map<string, PostLike>
): Theme[] {
  const groups = connectedComponents(centroids, coarseThreshold);

  return groups.map((indices, i) => {
    const themeMicroClusters = indices.map((idx) => microClusters[idx]);
    const allShortcodes = themeMicroClusters.flatMap((mc) => mc.postShortcodes);
    const themePosts = allShortcodes
      .map((sc) => postsByShortcode.get(sc))
      .filter((p): p is PostLike => Boolean(p));
    const { label, subLabels } = labelFromPosts(themePosts);
    return {
      id: `theme-${i}`,
      label,
      subLabels,
      postCount: allShortcodes.length,
      microClusters: themeMicroClusters,
    };
  });
}

export function computeThemes(
  posts: Post[],
  options?: ClusteringOptions
): { themes: Theme[]; unclusteredShortcodes: string[] } {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  const postsByShortcode = new Map<string, PostLike>(
    posts.map((p) => [p.shortcode, { tags: p.tags, category: p.category }])
  );

  const embeddedPosts: EmbeddedPost[] = [];
  posts.forEach((post, index) => {
    const vector = parseEmbedding(post.embedding);
    if (vector) embeddedPosts.push({ index, shortcode: post.shortcode, vector: normalize(vector) });
  });

  if (embeddedPosts.length === 0) {
    return { themes: [], unclusteredShortcodes: posts.map((p) => p.shortcode) };
  }

  const { microClusters, centroids } = buildMicroClusters(
    embeddedPosts,
    postsByShortcode,
    opts.fineThreshold
  );
  const themes = buildThemes(microClusters, centroids, opts.coarseThreshold, postsByShortcode)
    .filter((theme) => theme.postCount >= opts.minThemeSize)
    .sort((a, b) => b.postCount - a.postCount);

  const keptShortcodes = new Set(
    themes.flatMap((t) => t.microClusters.flatMap((mc) => mc.postShortcodes))
  );
  const unclusteredShortcodes = posts
    .map((p) => p.shortcode)
    .filter((sc) => !keptShortcodes.has(sc));

  return { themes, unclusteredShortcodes };
}
