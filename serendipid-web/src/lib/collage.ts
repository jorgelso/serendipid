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

// The seeded* helpers above all key off a numeric id (study guide
// collections/guides use their integer DB id directly). Boards use a
// uuid.hex string id instead, so this folds one down to a stable number to
// feed them — same purpose as Number(id) would serve for a numeric id.
export function hashSeed(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
