// Deterministic "randomness" for the study-guides corkboard aesthetic
// (src/components/PaperCutout.tsx etc.) — seeded off a stable id (a
// collection/guide's database id) rather than Math.random(), so a card's
// tilt/tape color doesn't visibly jump every time the page re-renders
// (which happens every few seconds while StudyGuideCorkboard is polling a
// still-generating collection).

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

// Hand-torn/die-cut paper silhouettes for PaperCutout.tsx — a handful of
// distinct jagged clip-path polygons (not a clean rectangle/rounded-rect)
// so the collage reads as scissor/hand-torn scraps, like the junk-journal
// references this was designed against. Kept moderately jagged rather than
// extreme — an aggressive tear risks clipping off real content at small
// card sizes.
export const TORN_CLIPS = [
  "polygon(0.5% 1.5%,12% 0%,27% 1.2%,41% 0%,58% 1%,74% 0%,88% 1.2%,100% 0.5%,99.3% 14%,100% 29%,98.8% 44%,100% 60%,99% 76%,100% 90%,88% 100%,73% 98.8%,59% 100%,44% 99%,28% 100%,13% 98.8%,0% 100%,1% 86%,0% 71%,1.2% 55%,0% 40%,1% 25%,0% 11%)",
  "polygon(0% 1%,10% 0%,24% 1.5%,39% 0.5%,53% 1.8%,68% 0.2%,83% 1.5%,100% 0%,98.5% 13%,100% 27%,98.2% 42%,100% 57%,98.8% 73%,100% 88%,90% 100%,76% 98.5%,61% 100%,47% 98.2%,33% 100%,19% 98.5%,4% 100%,0% 85%,1.5% 69%,0% 54%,1.8% 39%,0% 24%,1.2% 9%)",
  "polygon(1% 0%,16% 1.2%,31% 0%,47% 1%,63% 0%,79% 1.2%,94% 0%,100% 11%,98.5% 26%,100% 41%,99% 57%,100% 72%,98.2% 87%,100% 100%,84% 99%,69% 100%,54% 98.8%,38% 100%,22% 99%,6% 100%,0% 89%,1.2% 74%,0% 59%,1.5% 43%,0% 28%,1% 13%)",
];

export function seededTornClip(seed: number): string {
  return TORN_CLIPS[Math.abs(Math.floor(seed)) % TORN_CLIPS.length];
}
