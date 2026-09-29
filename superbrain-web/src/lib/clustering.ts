// Two-pass hierarchical clustering over stored post embeddings.
//
// Pass 1 (fine): connect posts whose embeddings are highly similar into tight
// micro-clusters (e.g. "guitar tutorials").
// Pass 2 (coarse): cluster the micro-clusters' centroids at a lower threshold,
// merging related micro-clusters into broader themes (e.g. guitar + violin +
// piano micro-clusters -> "Musical instruments").
//
// Pure functions, no I/O — computeThemes() is the entrypoint used by cache.ts.

import { UndirectedGraph } from "graphology";
import louvain from "graphology-communities-louvain";
import type { MicroCluster, Post, Theme } from "@/types/domain";

export interface EmbeddedPost {
  index: number;
  shortcode: string;
  vector: Float32Array; // pre-normalized (see fetchEmbeddings)
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

/** normalize() without the copy — for the freshly decoded /embeddings
 * buffer (src/lib/apiClient.ts fetchEmbeddings), which nothing else holds. */
export function normalizeInPlace(v: Float32Array): void {
  let sumSq = 0;
  for (let i = 0; i < v.length; i++) sumSq += v[i] * v[i];
  const norm = Math.sqrt(sumSq);
  if (norm === 0) return;
  for (let i = 0; i < v.length; i++) v[i] /= norm;
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

export interface MergedCluster {
  members: number[];
  centroid: Float32Array;
}

/** Graph-based community detection over a set of vectors (here, micro-cluster
 * centroids, weighted by each micro-cluster's post count) — replaces the
 * earlier threshold-based linkage approaches (single-link connectedComponents,
 * average-/centroid-link agglomerativeMerge). Those all shared a structural
 * flaw: a single global similarity threshold can't simultaneously be right
 * for a tight, dense topic and a diffuse, broad one, and any threshold-based
 * merge can be dragged along by a "hub" topic (e.g. self-improvement) that's
 * weakly similar to a lot of unrelated content — nothing stops it from
 * absorbing anything above the cutoff.
 *
 * Instead: build a mutual k-nearest-neighbor graph (an edge between two
 * micro-clusters only if each is among the other's own top-k most similar —
 * this is what prunes the one-sided "weakly similar to everything" edges a
 * hub topic accumulates, which a plain/one-sided k-NN graph would keep), then
 * run Louvain modularity optimization to find communities. This is locally
 * adaptive to density (no single global cutoff) and modularity is resistant
 * to a hub absorbing everything, since that requires genuinely dense mutual
 * connectivity, not just many weak one-directional similarities. */
export function louvainMerge(
  vectors: Float32Array[],
  weights: number[],
  options: { k: number; resolution: number; minSimilarity: number }
): MergedCluster[] {
  const n = vectors.length;
  if (n === 0) return [];
  if (n === 1) return [{ members: [0], centroid: vectors[0] }];

  const k = Math.min(options.k, n - 1);

  const sim: number[][] = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const s = dot(vectors[i], vectors[j]);
      sim[i][j] = s;
      sim[j][i] = s;
    }
  }

  const topK: number[][] = [];
  for (let i = 0; i < n; i++) {
    const ranked = Array.from({ length: n }, (_, j) => j)
      .filter((j) => j !== i)
      .sort((a, b) => sim[i][b] - sim[i][a])
      .slice(0, k);
    topK.push(ranked);
  }
  const topKSets = topK.map((neighbors) => new Set(neighbors));

  const graph = new UndirectedGraph();
  for (let i = 0; i < n; i++) graph.addNode(i);

  for (let i = 0; i < n; i++) {
    for (const j of topK[i]) {
      if (j <= i) continue;
      if (!topKSets[j].has(i)) continue; // mutual only
      const s = sim[i][j];
      if (s < options.minSimilarity) continue;
      graph.addEdge(i, j, { weight: s });
    }
  }

  const communities = louvain(graph, { resolution: options.resolution, getEdgeWeight: "weight" });

  const groups = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const communityId = communities[String(i)];
    const members = groups.get(communityId);
    if (members) members.push(i);
    else groups.set(communityId, [i]);
  }

  return Array.from(groups.values()).map((members) => {
    if (members.length === 1) return { members, centroid: vectors[members[0]] };
    const totalWeight = members.reduce((sum, idx) => sum + weights[idx], 0);
    const dim = vectors[0].length;
    const merged = new Float32Array(dim);
    for (const idx of members) {
      const w = weights[idx];
      for (let d = 0; d < dim; d++) merged[d] += vectors[idx][d] * w;
    }
    for (let d = 0; d < dim; d++) merged[d] /= totalWeight;
    return { members, centroid: normalize(merged) };
  });
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
  category: string[];
}

// Boilerplate hashtags that show up on almost every Instagram reel regardless
// of topic (platform/format noise, not content signal) — excluded from
// labeling only, not from clustering itself (that's driven by embeddings).
// Exported for reuse by src/lib/ideas.ts's tag-frequency aggregation, which
// wants the same "ignore platform noise" rule this module already encodes.
export const GENERIC_TAGS = new Set([
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

export function normalizeTag(tag: string): string {
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
    for (const category of post.category) {
      categoryFreq.set(category, (categoryFreq.get(category) ?? 0) + 1);
    }
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
  // Coarse-pass graph params (see louvainMerge()): how many nearest
  // neighbors each micro-cluster connects to before mutual-kNN pruning,
  // Louvain's modularity resolution (higher = more, smaller communities),
  // and a sanity floor so even a mutual top-k edge can't be near-meaningless.
  kNeighbors?: number;
  louvainResolution?: number;
  graphMinSimilarity?: number;
  minThemeSize?: number;
  // Bar for folding a sub-minThemeSize leftover group into an existing
  // theme (see buildThemes()) instead of leaving it unclustered. Lower than
  // graphMinSimilarity on purpose — leftovers are disproportionately small/
  // singleton micro-clusters with noisier, less-averaged centroids, so
  // holding them to the coarse-pass bar would absorb almost nothing.
  absorptionThreshold?: number;
  // Required gap between a leftover's best- and second-best-matching theme
  // for absorption to happen — keeps genuinely ambiguous leftovers (sitting
  // between two themes) unclustered rather than force-fit into whichever
  // theme happens to be marginally closer.
  absorptionMargin?: number;
}

const DEFAULT_OPTIONS: Required<ClusteringOptions> = {
  fineThreshold: 0.72,
  kNeighbors: 15,
  louvainResolution: 1,
  graphMinSimilarity: 0.5,
  minThemeSize: 3,
  absorptionThreshold: 0.65,
  absorptionMargin: 0.03,
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
  graphOptions: { k: number; resolution: number; minSimilarity: number },
  minThemeSize: number,
  absorptionThreshold: number,
  absorptionMargin: number,
  postsByShortcode: Map<string, PostLike>
): Theme[] {
  const weights = microClusters.map((mc) => mc.postShortcodes.length);
  const groups = louvainMerge(centroids, weights, graphOptions);

  interface ThemeGroup {
    microClusters: MicroCluster[];
    centroid: Float32Array;
  }

  const themeGroups: ThemeGroup[] = [];
  const leftovers: ThemeGroup[] = [];
  for (const group of groups) {
    const themeMicroClusters = group.members.map((idx) => microClusters[idx]);
    const postCount = themeMicroClusters.reduce((sum, mc) => sum + mc.postShortcodes.length, 0);
    const entry: ThemeGroup = { microClusters: themeMicroClusters, centroid: group.centroid };
    if (postCount >= minThemeSize) themeGroups.push(entry);
    else leftovers.push(entry);
  }

  // Balanced absorption: fold a leftover into the nearest theme only when
  // it's unambiguously closer to that one theme than to any other — a
  // leftover genuinely between two themes stays unclustered instead of
  // being force-fit.
  for (const leftover of leftovers) {
    let bestIdx = -1;
    let bestSim = -Infinity;
    let secondBestSim = -Infinity;
    themeGroups.forEach((theme, idx) => {
      const s = dot(leftover.centroid, theme.centroid);
      if (s > bestSim) {
        secondBestSim = bestSim;
        bestSim = s;
        bestIdx = idx;
      } else if (s > secondBestSim) {
        secondBestSim = s;
      }
    });
    if (bestIdx === -1) continue;
    const margin = secondBestSim === -Infinity ? Infinity : bestSim - secondBestSim;
    if (bestSim >= absorptionThreshold && margin >= absorptionMargin) {
      themeGroups[bestIdx].microClusters.push(...leftover.microClusters);
    }
  }

  return themeGroups.map((group, i) => {
    const allShortcodes = group.microClusters.flatMap((mc) => mc.postShortcodes);
    const themePosts = allShortcodes
      .map((sc) => postsByShortcode.get(sc))
      .filter((p): p is PostLike => Boolean(p));
    const { label, subLabels } = labelFromPosts(themePosts);
    return {
      id: `theme-${i}`,
      label,
      subLabels,
      postCount: allShortcodes.length,
      microClusters: group.microClusters,
    };
  });
}

export function computeThemes(
  posts: Post[],
  embeddings: Map<string, Float32Array>,
  options?: ClusteringOptions
): { themes: Theme[]; unclusteredShortcodes: string[] } {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  const postsByShortcode = new Map<string, PostLike>(
    posts.map((p) => [p.shortcode, { tags: p.tags, category: p.category }])
  );

  const embeddedPosts: EmbeddedPost[] = [];
  posts.forEach((post, index) => {
    const vector = embeddings.get(post.shortcode);
    if (vector) embeddedPosts.push({ index, shortcode: post.shortcode, vector });
  });

  if (embeddedPosts.length === 0) {
    return { themes: [], unclusteredShortcodes: posts.map((p) => p.shortcode) };
  }

  const { microClusters, centroids } = buildMicroClusters(
    embeddedPosts,
    postsByShortcode,
    opts.fineThreshold
  );
  const themes = buildThemes(
    microClusters,
    centroids,
    { k: opts.kNeighbors, resolution: opts.louvainResolution, minSimilarity: opts.graphMinSimilarity },
    opts.minThemeSize,
    opts.absorptionThreshold,
    opts.absorptionMargin,
    postsByShortcode
  ).sort((a, b) => b.postCount - a.postCount);

  const keptShortcodes = new Set(
    themes.flatMap((t) => t.microClusters.flatMap((mc) => mc.postShortcodes))
  );
  const unclusteredShortcodes = posts
    .map((p) => p.shortcode)
    .filter((sc) => !keptShortcodes.has(sc));

  return { themes, unclusteredShortcodes };
}

/** Nearest neighbors of a single post by embedding cosine similarity — a
 * simple O(n) point-to-all comparison, not the full two-pass clustering
 * above (no need for micro-clusters/themes just to rank "what's like this
 * one post"). Powers the dedicated post page's "related" section. */
export function findRelatedPosts(
  target: Post,
  posts: Post[],
  embeddings: Map<string, Float32Array>,
  limit = 8
): { shortcode: string; similarity: number }[] {
  const targetVector = embeddings.get(target.shortcode);
  if (!targetVector) return [];

  const scored: { shortcode: string; similarity: number }[] = [];
  for (const post of posts) {
    if (post.shortcode === target.shortcode) continue;
    const vector = embeddings.get(post.shortcode);
    if (!vector) continue;
    scored.push({
      shortcode: post.shortcode,
      similarity: dot(targetVector, vector),
    });
  }

  scored.sort((a, b) => b.similarity - a.similarity);
  return scored.slice(0, limit);
}
