// Home page recommendation engine — three independently callable scorers
// (cluster-affinity, interest-vector, hybrid) over the same raw signals:
// implicit view history, study-guide-source history (posts used to generate
// a study guide — a real but weaker interest signal than an actual
// qualifying view, see STUDY_GUIDE_WEIGHT below), search/chat query history,
// and the two manual ratings (enjoyment_rating / perceived_importance_rating).
//
// Server-only (never imported by a "use client" component) — reads full
// Post.embedding via getExport(), same embedding-never-reaches-the-browser
// rule as clustering.ts/vectorSpace.ts.
//
// Hard constraint: clustering itself is untouched. Every post->theme mapping
// here is read live from getThemes() on each call — no cluster id is ever
// persisted or passed in from outside this module.

import { getEmbeddings, getExport, getThemes } from "./cache";
import { fetchSearchHistory, fetchStudyGuideReelHistory, fetchViewHistory } from "./apiClient";
import { centroid, dot, normalize } from "./clustering";
import type {
  Post,
  RecommendationStrategy,
  SearchHistoryEntry,
  StudyGuideReelHistoryEntry,
  Theme,
  ViewHistoryEntry,
} from "@/types/domain";

export interface RecommendationItem {
  shortcode: string;
  score: number;
  reason: string;
}

export interface RecommendationsResult {
  strategy: RecommendationStrategy;
  items: RecommendationItem[];
  coldStart: boolean;
}

const DAY_MS = 24 * 60 * 60 * 1000;

// Shared across all three scorers so "watched a lot, but only ever a long
// time ago" and "searched this once, ages ago" decay the same way a scorer
// ranks a post from.
const RECENCY_HALF_LIFE_DAYS = 30;
const RATING_WEIGHT: Record<"liked" | "loved", number> = { liked: 2, loved: 4 };
const VIEW_WEIGHT = 1;
// Deliberately well below VIEW_WEIGHT — choosing a post as study-guide
// source material is real signal (you cared enough to synthesize it), but
// weaker than actually watching it, and must never outrank real views.
const STUDY_GUIDE_WEIGHT = 0.3;
const SEARCH_WEIGHT = 0.5;
// A post viewed within this window is assumed still "fresh in mind" and
// excluded from candidacy — recommending something just opened isn't useful.
const RECENT_VIEW_EXCLUSION_DAYS = 7;
// How many top-affinity theme buckets the cluster/hybrid scorers pull from.
const TOP_BUCKET_COUNT = 6;

function recencyWeight(isoTimestamp: string, now: number, halfLifeDays = RECENCY_HALF_LIFE_DAYS): number {
  const ts = Date.parse(isoTimestamp);
  if (!Number.isFinite(ts)) return 0;
  const ageDays = Math.max(0, (now - ts) / DAY_MS);
  return Math.pow(0.5, ageDays / halfLifeDays);
}

function ratingBoost(post: Post): number {
  let boost = 0;
  if (post.enjoyment_rating) boost += RATING_WEIGHT[post.enjoyment_rating as "liked" | "loved"];
  if (post.perceived_importance_rating) {
    boost += RATING_WEIGHT[post.perceived_importance_rating as "liked" | "loved"];
  }
  return boost;
}

interface Signals {
  posts: Post[];
  postsByShortcode: Map<string, Post>;
  embeddingByShortcode: Map<string, Float32Array>;
  themes: Theme[];
  // shortcode -> themeId | "unclustered", read fresh from getThemes() every
  // call — never a stored/persisted cluster id.
  themeOf: Map<string, string>;
  themeCentroids: Map<string, Float32Array>;
  views: ViewHistoryEntry[];
  viewsByShortcode: Map<string, ViewHistoryEntry[]>;
  studyGuideReels: StudyGuideReelHistoryEntry[];
  studyGuideReelsByShortcode: Map<string, StudyGuideReelHistoryEntry[]>;
  searches: SearchHistoryEntry[];
  now: number;
}

async function loadSignals(): Promise<Signals> {
  const [
    { posts },
    { themes, unclusteredShortcodes },
    embeddingByShortcode,
    viewHistoryResp,
    studyGuideReelHistoryResp,
    searchHistoryResp,
  ] =
    await Promise.all([
      getExport(),
      getThemes(),
      getEmbeddings(),
      fetchViewHistory(),
      fetchStudyGuideReelHistory(),
      fetchSearchHistory(),
    ]);

  const postsByShortcode = new Map(posts.map((p) => [p.shortcode, p]));


  const themeOf = new Map<string, string>();
  for (const sc of unclusteredShortcodes) themeOf.set(sc, "unclustered");
  for (const theme of themes) {
    for (const mc of theme.microClusters) {
      for (const sc of mc.postShortcodes) themeOf.set(sc, theme.id);
    }
  }
  // Defensive: a post absent from both lists (shouldn't happen) still gets a
  // bucket rather than silently dropping out of candidacy.
  for (const post of posts) {
    if (!themeOf.has(post.shortcode)) themeOf.set(post.shortcode, "unclustered");
  }

  const themeCentroids = new Map<string, Float32Array>();
  for (const theme of themes) {
    const vecs: Float32Array[] = [];
    for (const mc of theme.microClusters) {
      for (const sc of mc.postShortcodes) {
        const v = embeddingByShortcode.get(sc);
        if (v) vecs.push(v);
      }
    }
    if (vecs.length > 0) themeCentroids.set(theme.id, centroid(vecs));
  }

  const views = viewHistoryResp.data;
  const viewsByShortcode = new Map<string, ViewHistoryEntry[]>();
  for (const v of views) {
    const list = viewsByShortcode.get(v.shortcode);
    if (list) list.push(v);
    else viewsByShortcode.set(v.shortcode, [v]);
  }

  const studyGuideReels = studyGuideReelHistoryResp.data;
  const studyGuideReelsByShortcode = new Map<string, StudyGuideReelHistoryEntry[]>();
  for (const r of studyGuideReels) {
    const list = studyGuideReelsByShortcode.get(r.shortcode);
    if (list) list.push(r);
    else studyGuideReelsByShortcode.set(r.shortcode, [r]);
  }

  return {
    posts,
    postsByShortcode,
    embeddingByShortcode,
    themes,
    themeOf,
    themeCentroids,
    views,
    viewsByShortcode,
    studyGuideReels,
    studyGuideReelsByShortcode,
    searches: searchHistoryResp.data,
    now: Date.now(),
  };
}

function isColdStart(signals: Signals): boolean {
  if (signals.views.length > 0) return false;
  if (signals.studyGuideReels.length > 0) return false;
  if (signals.searches.length > 0) return false;
  return !signals.posts.some((p) => p.enjoyment_rating || p.perceived_importance_rating);
}

function fallback(strategy: RecommendationStrategy, posts: Post[], limit: number): RecommendationsResult {
  const sorted = [...posts].sort((a, b) => {
    const ai = a.importance ?? 0;
    const bi = b.importance ?? 0;
    if (bi !== ai) return bi - ai;
    return (Date.parse(b.analyzed_at ?? "") || 0) - (Date.parse(a.analyzed_at ?? "") || 0);
  });
  return {
    strategy,
    coldStart: true,
    items: sorted.slice(0, limit).map((p) => ({
      shortcode: p.shortcode,
      score: p.importance ?? 0,
      reason: "Not enough activity yet — showing your most important recent posts",
    })),
  };
}

// Per-event, recency-decayed sum — NOT a flat view count. Watching the same
// post 5 times recently outscores watching it once; watching it 5 times a
// year ago and never since decays back toward ~0, same as a single old view
// would, rather than a flat multiplier keeping it artificially high forever.
function viewScore(shortcode: string, signals: Signals): number {
  const events = signals.viewsByShortcode.get(shortcode);
  if (!events) return 0;
  let total = 0;
  for (const v of events) total += recencyWeight(v.viewed_at, signals.now);
  return VIEW_WEIGHT * total;
}

// The timestamp a single study-guide link's recency decays from: whichever
// is more recent, when it was made or when its collection was last opened.
// Reopening an old study guide is a fresh "I still care about this" event,
// so it resets the decay the same way a rewatch does for a real view,
// rather than the link's importance only ever fading from its creation date.
function studyGuideEventTimestamp(entry: StudyGuideReelHistoryEntry): string {
  if (!entry.opened_at) return entry.created_at;
  return Date.parse(entry.opened_at) > Date.parse(entry.created_at) ? entry.opened_at : entry.created_at;
}

// Same per-event, recency-decayed sum as viewScore, scaled down by
// STUDY_GUIDE_WEIGHT — the same reel used as source material for several
// study guides (or a study guide reopened many times) outscores a single
// old, never-reopened one, but never outscores an actual qualifying view.
function studyGuideScore(shortcode: string, signals: Signals): number {
  const events = signals.studyGuideReelsByShortcode.get(shortcode);
  if (!events) return 0;
  let total = 0;
  for (const e of events) total += recencyWeight(studyGuideEventTimestamp(e), signals.now);
  return STUDY_GUIDE_WEIGHT * total;
}

// 0 (viewed very recently) -> 1 (never viewed, or viewed a very long time
// ago) — "surface important-but-stale posts" needs this, not raw recency.
function stalenessBonus(shortcode: string, signals: Signals): number {
  const events = signals.viewsByShortcode.get(shortcode);
  if (!events || events.length === 0) return 1;
  let mostRecentTs = 0;
  for (const v of events) {
    const t = Date.parse(v.viewed_at);
    if (Number.isFinite(t)) mostRecentTs = Math.max(mostRecentTs, t);
  }
  if (mostRecentTs === 0) return 1;
  const ageDays = Math.max(0, (signals.now - mostRecentTs) / DAY_MS);
  return 1 - Math.pow(0.5, ageDays / RECENCY_HALF_LIFE_DAYS);
}

function recentlyViewedShortcodes(signals: Signals, windowDays = RECENT_VIEW_EXCLUSION_DAYS): Set<string> {
  const cutoff = signals.now - windowDays * DAY_MS;
  const out = new Set<string>();
  for (const v of signals.views) {
    const ts = Date.parse(v.viewed_at);
    if (Number.isFinite(ts) && ts >= cutoff) out.add(v.shortcode);
  }
  return out;
}

function membersByBucket(signals: Signals): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const [shortcode, themeId] of signals.themeOf) {
    const list = map.get(themeId);
    if (list) list.push(shortcode);
    else map.set(themeId, [shortcode]);
  }
  return map;
}

// Recency-weighted affinity per theme bucket (including an explicit
// "unclustered" pseudo-bucket, never dropped) — built from views mapped to
// each post's CURRENT theme, rated posts, and search-query similarity to
// theme centroids. "unclustered" has no centroid, so it only accrues
// affinity from direct engagement (views/ratings), never from query
// similarity — it still competes for a top-bucket slot on that basis alone.
function computeClusterAffinity(signals: Signals): Map<string, number> {
  const affinity = new Map<string, number>();
  const bump = (id: string, amount: number) => {
    if (amount <= 0) return;
    affinity.set(id, (affinity.get(id) ?? 0) + amount);
  };

  for (const [shortcode, events] of signals.viewsByShortcode) {
    const themeId = signals.themeOf.get(shortcode);
    if (!themeId) continue;
    let w = 0;
    for (const v of events) w += recencyWeight(v.viewed_at, signals.now);
    bump(themeId, VIEW_WEIGHT * w);
  }

  for (const [shortcode, events] of signals.studyGuideReelsByShortcode) {
    const themeId = signals.themeOf.get(shortcode);
    if (!themeId) continue;
    let w = 0;
    for (const e of events) w += recencyWeight(studyGuideEventTimestamp(e), signals.now);
    bump(themeId, STUDY_GUIDE_WEIGHT * w);
  }

  for (const post of signals.posts) {
    const themeId = signals.themeOf.get(post.shortcode);
    if (!themeId) continue;
    bump(themeId, ratingBoost(post));
  }

  for (const s of signals.searches) {
    if (!s.query_embedding) continue;
    const qVec = normalize(Float32Array.from(s.query_embedding));
    const w = SEARCH_WEIGHT * recencyWeight(s.created_at, signals.now);
    if (w <= 0) continue;
    for (const [themeId, centroidVec] of signals.themeCentroids) {
      const sim = dot(qVec, centroidVec);
      if (sim > 0) bump(themeId, w * sim);
    }
  }

  return affinity;
}

// Single rolling embedding = recency-weighted average of view/rating/search
// embeddings, ratings weighted heaviest. Returns null when there's nothing
// to build one from (cold start, or no post/query has an embedding yet).
function computeInterestVector(signals: Signals): Float32Array | null {
  let acc: Float32Array | null = null;
  let totalWeight = 0;

  function accumulate(vec: Float32Array, weight: number) {
    if (weight <= 0) return;
    if (!acc) acc = new Float32Array(vec.length);
    for (let i = 0; i < vec.length; i++) acc[i] += vec[i] * weight;
    totalWeight += weight;
  }

  for (const [shortcode] of signals.viewsByShortcode) {
    const vec = signals.embeddingByShortcode.get(shortcode);
    if (!vec) continue;
    accumulate(vec, viewScore(shortcode, signals));
  }

  for (const [shortcode] of signals.studyGuideReelsByShortcode) {
    const vec = signals.embeddingByShortcode.get(shortcode);
    if (!vec) continue;
    accumulate(vec, studyGuideScore(shortcode, signals));
  }

  for (const post of signals.posts) {
    const boost = ratingBoost(post);
    if (boost <= 0) continue;
    const vec = signals.embeddingByShortcode.get(post.shortcode);
    if (!vec) continue;
    accumulate(vec, boost);
  }

  for (const s of signals.searches) {
    if (!s.query_embedding) continue;
    const vec = normalize(Float32Array.from(s.query_embedding));
    accumulate(vec, SEARCH_WEIGHT * recencyWeight(s.created_at, signals.now));
  }

  if (!acc || totalWeight <= 0) return null;
  return normalize(acc);
}

// Scorer 1: cluster picks which theme buckets to pull from; within a
// bucket, candidates are ranked by importance + staleness (no embedding
// similarity here — that's what distinguishes this scorer from hybrid).
export async function scoreClusterAffinity(limit: number): Promise<RecommendationsResult> {
  const signals = await loadSignals();
  if (isColdStart(signals)) return fallback("cluster", signals.posts, limit);

  const affinity = computeClusterAffinity(signals);
  const rankedBuckets = Array.from(affinity.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_BUCKET_COUNT)
    .map(([id]) => id);

  const excluded = recentlyViewedShortcodes(signals);
  const buckets = membersByBucket(signals);
  const items: RecommendationItem[] = [];
  const seen = new Set<string>();

  for (const bucketId of rankedBuckets) {
    if (items.length >= limit) break;
    const label =
      bucketId === "unclustered" ? "posts you haven't sorted into a theme yet" : (signals.themes.find((t) => t.id === bucketId)?.label ?? bucketId);

    const ranked = (buckets.get(bucketId) ?? [])
      .filter((sc) => !excluded.has(sc) && !seen.has(sc))
      .map((sc) => signals.postsByShortcode.get(sc))
      .filter((p): p is Post => Boolean(p))
      .map((p) => ({
        shortcode: p.shortcode,
        score: 0.6 * ((p.importance ?? 3) / 5) + 0.4 * stalenessBonus(p.shortcode, signals),
        reason: `From your top theme: ${label}`,
      }))
      .sort((a, b) => b.score - a.score);

    for (const item of ranked) {
      if (items.length >= limit) break;
      if (seen.has(item.shortcode)) continue;
      seen.add(item.shortcode);
      items.push(item);
    }
  }

  return { strategy: "cluster", coldStart: false, items };
}

// Scorer 2: one rolling embedding, rank every not-recently-viewed post by
// cosine similarity to it.
export async function scoreInterestVector(limit: number): Promise<RecommendationsResult> {
  const signals = await loadSignals();
  if (isColdStart(signals)) return fallback("vector", signals.posts, limit);

  const vector = computeInterestVector(signals);
  if (!vector) return fallback("vector", signals.posts, limit);

  const excluded = recentlyViewedShortcodes(signals);
  const items: RecommendationItem[] = [];
  for (const post of signals.posts) {
    if (excluded.has(post.shortcode)) continue;
    const vec = signals.embeddingByShortcode.get(post.shortcode);
    if (!vec) continue;
    items.push({
      shortcode: post.shortcode,
      score: dot(vector, vec),
      reason: "Similar to what you've been engaging with",
    });
  }
  items.sort((a, b) => b.score - a.score);
  return { strategy: "vector", coldStart: false, items: items.slice(0, limit) };
}

// Scorer 3 (the original ask): cluster-affinity picks which theme buckets to
// pull from; within each, embedding similarity to the interest vector picks
// which posts, blended with importance/staleness. Unclustered candidates are
// never excluded just because their cluster is uncategorized — they're
// always scored by pure embedding similarity, bypassing bucket/affinity
// gating entirely, rather than needing "unclustered" to win a top-bucket slot.
export async function scoreHybrid(limit: number): Promise<RecommendationsResult> {
  const signals = await loadSignals();
  if (isColdStart(signals)) return fallback("hybrid", signals.posts, limit);

  const affinity = computeClusterAffinity(signals);
  const rankedThemeBuckets = Array.from(affinity.entries())
    .filter(([id]) => id !== "unclustered")
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_BUCKET_COUNT)
    .map(([id]) => id);

  const vector = computeInterestVector(signals);
  const excluded = recentlyViewedShortcodes(signals);
  const buckets = membersByBucket(signals);

  function scoreCandidate(post: Post, reason: string): RecommendationItem {
    const vec = signals.embeddingByShortcode.get(post.shortcode);
    const similarity = vector && vec ? Math.max(0, dot(vector, vec)) : 0;
    const importanceNorm = (post.importance ?? 3) / 5;
    const staleness = stalenessBonus(post.shortcode, signals);
    const score = 0.6 * similarity + 0.25 * importanceNorm + 0.15 * staleness;
    return { shortcode: post.shortcode, score, reason };
  }

  const items: RecommendationItem[] = [];
  const seen = new Set<string>();

  for (const themeId of rankedThemeBuckets) {
    const label = signals.themes.find((t) => t.id === themeId)?.label ?? themeId;
    const members = (buckets.get(themeId) ?? [])
      .filter((sc) => !excluded.has(sc) && !seen.has(sc))
      .map((sc) => signals.postsByShortcode.get(sc))
      .filter((p): p is Post => Boolean(p));

    const ranked = members
      .map((p) => scoreCandidate(p, `From your top theme: ${label}`))
      .sort((a, b) => b.score - a.score);

    for (const item of ranked) {
      if (seen.has(item.shortcode)) continue;
      seen.add(item.shortcode);
      items.push(item);
    }
  }

  const unclusteredMembers = (buckets.get("unclustered") ?? [])
    .filter((sc) => !excluded.has(sc) && !seen.has(sc))
    .map((sc) => signals.postsByShortcode.get(sc))
    .filter((p): p is Post => Boolean(p));

  for (const item of unclusteredMembers
    .map((p) => scoreCandidate(p, "Similar to what you've been engaging with"))
    .sort((a, b) => b.score - a.score)) {
    if (seen.has(item.shortcode)) continue;
    seen.add(item.shortcode);
    items.push(item);
  }

  items.sort((a, b) => b.score - a.score);
  return { strategy: "hybrid", coldStart: false, items: items.slice(0, limit) };
}

export async function getRecommendations(
  strategy: RecommendationStrategy,
  limit: number
): Promise<RecommendationsResult> {
  switch (strategy) {
    case "cluster":
      return scoreClusterAffinity(limit);
    case "vector":
      return scoreInterestVector(limit);
    case "hybrid":
      return scoreHybrid(limit);
  }
}
