// Projects every post's 1536-dim embedding down to 3D (UMAP) for the /space
// view, and reuses computeThemes()'s cosine-similarity clusters (src/lib/
// clustering.ts) to color the result instead of re-clustering from scratch.
//
// Pure functions, no I/O — computeVectorSpaceLayout() is the entrypoint used
// by cache.ts, same shape as computeThemes().

import { UMAP } from "umap-js";
import type { Post, Theme, VectorSpaceColorSlot, VectorSpacePoint } from "@/types/domain";
import { centroid, dot, normalize, parseEmbedding } from "./clustering";
import { classifyMedia } from "./media";
import { resolveMediaUrls } from "./posts";

// A fixed seed keeps the layout stable across recomputes (cache invalidation
// after an edit/reanalyze) instead of the whole scene jumping every time —
// UMAP is stochastic unless its RNG is seeded. Deterministic, not
// cryptographic: https://github.com/bryc/code/blob/master/jshash/PRNGs.md
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const UMAP_SEED = 0x53757065; // "Supe" — arbitrary, just fixed
const TARGET_RADIUS = 24;

interface ThemeAssignment {
  colorSlot: VectorSpaceColorSlot;
  themeId: string;
  themeLabel: string;
}

// The first 8 themes (already sorted largest-first by computeThemes()) get
// one of the 8 validated categorical hues (globals.css --viz-series-1..8);
// everything past that folds into "other" rather than cycling colors, per
// the dataviz skill's scatter/all-pairs series cap.
function buildThemeAssignments(themes: Theme[]): Map<string, ThemeAssignment> {
  const bySh = new Map<string, ThemeAssignment>();
  themes.forEach((theme, themeIndex) => {
    const assignment: ThemeAssignment = {
      colorSlot: themeIndex < 8 ? `theme-${themeIndex}` : "other",
      themeId: theme.id,
      themeLabel: theme.label,
    };
    for (const microCluster of theme.microClusters) {
      for (const shortcode of microCluster.postShortcodes) {
        bySh.set(shortcode, assignment);
      }
    }
  });
  return bySh;
}

// How close a post's similarity to a *second* theme's centroid has to be to
// its own theme's, before that second theme is blended into its dot color
// (e.g. an "AI ethics" post sitting between an AI theme and a religion
// theme). 0 => tied with its own theme (full 50/50 blend); this margin =>
// no longer close enough to blend at all.
const BLEND_SIMILARITY_MARGIN = 0.05;

interface ThemeBlend {
  colorSlot: VectorSpaceColorSlot;
  weight: number; // 0-0.5
}

/** For a post whose embedding sits close to a second theme's centroid as
 * well as its own assigned one, returns the second theme's color slot and
 * how much of it to blend in (0 at the margin's edge, up to 0.5 for a tie).
 * Returns null when the post isn't meaningfully "between" two themes. */
function computeThemeBlend(
  vector: Float32Array,
  ownThemeId: string,
  themeCentroids: Map<string, Float32Array>,
  themeColorSlots: Map<string, VectorSpaceColorSlot>
): ThemeBlend | null {
  const ownCentroid = themeCentroids.get(ownThemeId);
  if (!ownCentroid) return null;
  const ownSim = dot(vector, ownCentroid);

  let bestOtherThemeId: string | null = null;
  let bestOtherSim = -Infinity;
  for (const [themeId, themeCentroidVector] of themeCentroids) {
    if (themeId === ownThemeId) continue;
    const s = dot(vector, themeCentroidVector);
    if (s > bestOtherSim) {
      bestOtherSim = s;
      bestOtherThemeId = themeId;
    }
  }
  if (!bestOtherThemeId) return null;

  const gap = Math.min(Math.max(ownSim - bestOtherSim, 0), BLEND_SIMILARITY_MARGIN);
  if (gap >= BLEND_SIMILARITY_MARGIN) return null;

  const colorSlot = themeColorSlots.get(bestOtherThemeId);
  if (!colorSlot) return null;

  return { colorSlot, weight: 0.5 * (1 - gap / BLEND_SIMILARITY_MARGIN) };
}

/** Recenters on the centroid and uniformly rescales (same factor on every
 * axis, so relative distances — the whole point of this view — aren't
 * distorted) to a consistent on-screen radius regardless of UMAP's
 * dataset-dependent raw output scale. */
function normalizeLayout(raw: number[][]): [number, number, number][] {
  const n = raw.length;
  if (n === 0) return [];

  const centroid = [0, 0, 0];
  for (const p of raw) {
    centroid[0] += p[0];
    centroid[1] += p[1];
    centroid[2] += p[2];
  }
  centroid[0] /= n;
  centroid[1] /= n;
  centroid[2] /= n;

  let maxDist = 0;
  for (const p of raw) {
    const dx = p[0] - centroid[0];
    const dy = p[1] - centroid[1];
    const dz = (p[2] ?? 0) - centroid[2];
    maxDist = Math.max(maxDist, Math.sqrt(dx * dx + dy * dy + dz * dz));
  }
  const scale = maxDist > 0 ? TARGET_RADIUS / maxDist : 1;

  return raw.map((p) => [
    (p[0] - centroid[0]) * scale,
    (p[1] - centroid[1]) * scale,
    ((p[2] ?? 0) - centroid[2]) * scale,
  ]);
}

// UMAP routinely places very-similar posts almost exactly on top of each
// other, especially the "unclustered" majority (no theme is a strong enough
// pull to keep them apart) — great for measuring similarity, bad for a
// scene where you need to see and click individual points. A few rounds of
// simple pairwise repulsion (push apart any pair closer than MIN_SEPARATION,
// same idea as d3-force's collide) gives every point real breathing room
// without materially changing the overall cluster shape. O(n^2) per pass —
// fine at personal-library scale (a few hundred to low thousands of posts,
// computed once and cached alongside the rest of this layout); capped for
// safety if a library ever gets huge enough for that to matter.
const MIN_SEPARATION = 1.4;
const DECLUTTER_ITERATIONS = 6;
const DECLUTTER_MAX_POINTS = 4000;

function declutter(positions: [number, number, number][]): [number, number, number][] {
  if (positions.length > DECLUTTER_MAX_POINTS) return positions;
  const pts = positions.map((p) => [...p] as [number, number, number]);
  const random = mulberry32(UMAP_SEED ^ 0x9e3779b9);

  for (let iter = 0; iter < DECLUTTER_ITERATIONS; iter++) {
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[j][0] - pts[i][0];
        const dy = pts[j][1] - pts[i][1];
        const dz = pts[j][2] - pts[i][2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

        if (dist < 1e-6) {
          // Exact (or near-exact) overlap — nudge apart in a random
          // direction rather than dividing by a near-zero distance.
          const jitter = () => (random() - 0.5) * MIN_SEPARATION;
          pts[j][0] += jitter();
          pts[j][1] += jitter();
          pts[j][2] += jitter();
          continue;
        }
        if (dist >= MIN_SEPARATION) continue;

        const push = (MIN_SEPARATION - dist) / 2;
        const nx = (dx / dist) * push;
        const ny = (dy / dist) * push;
        const nz = (dz / dist) * push;
        pts[i][0] -= nx;
        pts[i][1] -= ny;
        pts[i][2] -= nz;
        pts[j][0] += nx;
        pts[j][1] += ny;
        pts[j][2] += nz;
      }
    }
  }

  return pts;
}

// DISABLED per user request — reverted to the neutral-slot-based glow
// dimming in VectorSpaceScene.tsx instead. Left in place (commented, not
// deleted) in case density-based glow scaling is wanted again later.
//
// However well-separated the layout is, a point buried in a tight cluster
// still has many neighbors nearby — its glow (see VectorSpaceScene's
// GlowLayer) should recede in proportion, so a dense area reads as distinct
// dots instead of a merged wash, while a genuinely isolated point keeps its
// full glow. Same O(n^2) pairwise-distance shape as declutter() above (and
// the same size cap), just counting instead of pushing.
// const DENSITY_RADIUS = 2.5;
// const DENSITY_SATURATION = 10; // neighbor count at which glow bottoms out
// const MIN_GLOW_SCALE = 0.35;
//
// function computeGlowScales(positions: [number, number, number][]): number[] {
//   const n = positions.length;
//   const neighborCounts = new Array(n).fill(0);
//   if (n > DECLUTTER_MAX_POINTS) return neighborCounts.map(() => 1);
//
//   const radiusSq = DENSITY_RADIUS * DENSITY_RADIUS;
//   for (let i = 0; i < n; i++) {
//     for (let j = i + 1; j < n; j++) {
//       const dx = positions[j][0] - positions[i][0];
//       const dy = positions[j][1] - positions[i][1];
//       const dz = positions[j][2] - positions[i][2];
//       if (dx * dx + dy * dy + dz * dz < radiusSq) {
//         neighborCounts[i]++;
//         neighborCounts[j]++;
//       }
//     }
//   }
//
//   return neighborCounts.map((count) => {
//     const t = Math.min(count, DENSITY_SATURATION) / DENSITY_SATURATION;
//     return 1 - t * (1 - MIN_GLOW_SCALE);
//   });
// }

/** Below this, UMAP's neighbor graph isn't meaningful (and nNeighbors can't
 * be clamped sensibly) — spread points on a small ring instead of crashing
 * or projecting garbage. A fresh library with a handful of saved reels hits
 * this path. */
function fallbackLayout(n: number): [number, number, number][] {
  if (n === 1) return [[0, 0, 0]];
  const positions: [number, number, number][] = [];
  for (let i = 0; i < n; i++) {
    const angle = (2 * Math.PI * i) / n;
    positions.push([Math.cos(angle) * TARGET_RADIUS * 0.3, 0, Math.sin(angle) * TARGET_RADIUS * 0.3]);
  }
  return positions;
}

const MIN_POINTS_FOR_UMAP = 4;

export function computeVectorSpaceLayout(
  posts: Post[],
  themes: Theme[],
  apiBaseUrl: string
): VectorSpacePoint[] {
  const postsByShortcode = new Map(posts.map((p) => [p.shortcode, p]));
  const themeAssignments = buildThemeAssignments(themes);

  const shortcodes: string[] = [];
  const vectors: number[][] = [];
  const vectorByShortcode = new Map<string, Float32Array>();
  posts.forEach((post) => {
    const vector = parseEmbedding(post.embedding);
    if (!vector) return;
    const normalized = normalize(vector);
    shortcodes.push(post.shortcode);
    vectors.push(Array.from(normalized));
    vectorByShortcode.set(post.shortcode, normalized);
  });

  if (vectors.length === 0) return [];

  // Every theme's centroid, computed from its actual member posts' vectors
  // (not just the coarse pass's micro-cluster centroids) — used below to
  // find posts that sit close to a *second* theme as well as their own, so
  // they can render as a blended color instead of a single hard-coded hue.
  const themeColorSlots = new Map<string, VectorSpaceColorSlot>();
  const themeCentroids = new Map<string, Float32Array>();
  themes.forEach((theme, themeIndex) => {
    themeColorSlots.set(theme.id, themeIndex < 8 ? `theme-${themeIndex}` : "other");
    const memberVectors = theme.microClusters
      .flatMap((mc) => mc.postShortcodes)
      .map((sc) => vectorByShortcode.get(sc))
      .filter((v): v is Float32Array => Boolean(v));
    if (memberVectors.length > 0) themeCentroids.set(theme.id, centroid(memberVectors));
  });

  const rawPositions =
    vectors.length < MIN_POINTS_FOR_UMAP
      ? fallbackLayout(vectors.length)
      : (() => {
          const nNeighbors = Math.max(2, Math.min(15, vectors.length - 1));
          const umap = new UMAP({
            nComponents: 3,
            nNeighbors,
            random: mulberry32(UMAP_SEED),
          });
          return umap.fit(vectors) as number[][];
        })();

  const positions = declutter(normalizeLayout(rawPositions));
  // const glowScales = computeGlowScales(positions); // disabled — see computeGlowScales' comment above

  return shortcodes.map((shortcode, i) => {
    const post = postsByShortcode.get(shortcode)!;
    const assignment = themeAssignments.get(shortcode);
    const mediaUrls = resolveMediaUrls(post.media_urls, apiBaseUrl);
    const videoUrl = classifyMedia(mediaUrls).videos[0] ?? null;

    const vector = vectorByShortcode.get(shortcode);
    const blend =
      vector && assignment?.themeId
        ? computeThemeBlend(vector, assignment.themeId, themeCentroids, themeColorSlots)
        : null;

    return {
      shortcode,
      position: positions[i],
      colorSlot: assignment?.colorSlot ?? "unclustered",
      themeId: assignment?.themeId ?? null,
      themeLabel: assignment?.themeLabel ?? "Unclustered",
      blendColorSlot: blend?.colorSlot ?? null,
      blendWeight: blend?.weight,
      title: post.title,
      category: post.category,
      // A short, cacheable proxy URL (see src/app/api/thumbnail) rather than
      // post.thumbnail directly — that field can be a data: URI with the
      // whole image inlined as base64, which would balloon this payload to
      // tens of MB across a few hundred points.
      thumbnail: post.thumbnail ? `/api/thumbnail/${post.shortcode}` : null,
      videoUrl,
      // glowScale: glowScales[i], // disabled — see computeGlowScales' comment above
    };
  });
}
