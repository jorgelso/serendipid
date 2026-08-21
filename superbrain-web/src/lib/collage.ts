// Deterministic "randomness" for the study-guides corkboard aesthetic —
// seeded off a stable id (a collection/guide's database id) rather than
// Math.random(), so a fragment's tilt/tape color/offset doesn't visibly
// jump every time the page re-renders (which happens every few seconds
// while StudyGuideCorkboard is polling a still-generating collection).

function seededFraction(seed: number): number {
  const x = Math.sin(seed * 999) * 10000;
  return x - Math.floor(x);
}

export function seededRotation(seed: number, range = 4): number {
  return Math.round((seededFraction(seed) * 2 - 1) * range * 10) / 10;
}

export const TAPE_COLORS = ["coral", "teal", "lavender", "yellow", "mint", "rose", "sky"] as const;
export type TapeColor = (typeof TAPE_COLORS)[number];

export function seededTapeColor(seed: number): TapeColor {
  return TAPE_COLORS[Math.abs(Math.floor(seed)) % TAPE_COLORS.length];
}

// A signed pixel jitter (not a rotation) — used to scatter overlapping
// collage fragments (fanned thumbnails, tags, tape) around an anchor point
// instead of stacking them dead-center, while staying deterministic per seed.
export function seededOffset(seed: number, range = 10): number {
  return Math.round((seededFraction(seed) * 2 - 1) * range);
}

// Deterministic stacking order for layered collage pieces — different seeds
// (e.g. collection.id vs. collection.id + 5) land in different bands so
// neighboring fragments don't all paint in the same order every time.
export function seededZIndex(seed: number, min = 1, max = 8): number {
  return min + Math.floor(seededFraction(seed * 1.37) * (max - min + 1));
}

// Hand-torn photo silhouettes for TornPhoto.tsx — jagged clip-path
// polygons (not a clean rectangle) so a source-post thumbnail reads as a
// scissor/hand-torn scrap rather than a cropped UI image.
const TORN_CLIPS = [
  "polygon(1% 4%,9% 0%,19% 3%,29% 0%,41% 4%,53% 0%,64% 3%,76% 0%,88% 4%,100% 1%,97% 12%,100% 24%,96% 36%,100% 48%,97% 60%,100% 72%,96% 84%,100% 96%,88% 100%,77% 97%,65% 100%,54% 96%,42% 100%,30% 97%,18% 100%,7% 96%,0% 100%,3% 88%,0% 76%,4% 64%,0% 52%,3% 40%,0% 28%,4% 16%,0% 8%)",
  "polygon(0% 2%,14% 0%,27% 3%,44% 0%,60% 2%,78% 0%,100% 3%,96% 15%,100% 30%,95% 46%,100% 62%,96% 78%,100% 94%,86% 100%,70% 97%,55% 100%,38% 97%,22% 100%,6% 97%,0% 88%,4% 70%,0% 54%,3% 38%,0% 22%,4% 10%)",
  "polygon(3% 0%,22% 2%,40% 0%,58% 3%,76% 0%,94% 2%,100% 14%,97% 28%,100% 44%,98% 60%,100% 76%,97% 90%,100% 100%,82% 98%,64% 100%,46% 97%,28% 100%,10% 98%,0% 86%,2% 70%,0% 54%,3% 38%,0% 22%,2% 8%)",
  "polygon(2% 0%,20% 3%,35% 0%,52% 2%,68% 0%,85% 3%,100% 0%,98% 18%,100% 36%,97% 54%,100% 72%,98% 90%,100% 100%,80% 97%,60% 100%,40% 97%,20% 100%,0% 96%,3% 78%,0% 60%,2% 42%,0% 24%,3% 10%)",
] as const;

export function seededTornClip(seed: number): string {
  return TORN_CLIPS[Math.abs(Math.floor(seed)) % TORN_CLIPS.length];
}

// A deterministic PRNG (mulberry32), not the sin-based seededFraction above —
// the dense collage scatter fill (StudyGuideCorkboard) draws dozens of
// values per collection (position, size, rotation, fragment type, asset
// pick...) and needs them to look uniformly scattered rather than fall into
// the faint periodicity sin(seed*999) shows over long sequential draws.
// Re-seeding with the same integer (collection.id) always replays the same
// sequence, which is what keeps the layout stable across the polling
// re-renders while a collection is still generating.
export function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function pick<T>(rng: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rng() * arr.length) % arr.length];
}
