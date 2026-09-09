import type { TapeColor } from "./collage";

export const NON_NULL_SOURCE_TYPES = ["board", "search", "cluster", "manual"] as const;
export type NonNullSourceType = (typeof NON_NULL_SOURCE_TYPES)[number];

export const SOURCE_TYPE_LABELS: Record<NonNullSourceType, string> = {
  board: "Board",
  search: "Search",
  cluster: "Cluster",
  manual: "Hand-picked",
};

// Fixed (not seeded/random) TapeColor per source type — the single source
// of truth for both the corkboard's title-chip color (CutoutChip's `color`
// override, StudyGuideCorkboard.tsx) and the legend's swatches
// (StudyGuideSourceLegend.tsx), so the two always match exactly. Mapped to
// read as plain red/purple/blue/green — a small, clearly-distinct set (not
// collage.ts's full seven-color palette, which packs in several similar
// pastels that are hard to tell apart at a glance and would make a
// "meaningful" color indistinguishable from a merely decorative one).
export const SOURCE_TYPE_TAPE_COLORS: Record<NonNullSourceType, TapeColor> = {
  board: "coral", // red
  search: "lavender", // purple
  cluster: "sky", // blue
  manual: "mint", // green
};

// The corkboard's fifth, fixed color for a collection whose source_label
// doesn't match any recognized prefix below — genuinely nothing to go on.
export const UNLABELED_TAPE_COLOR: TapeColor = "yellow";

// Every generation entry point stamps a human-readable source_label with a
// recognizable prefix — "Board: ...", "Search: ...", "Theme: ...",
// "Idea: ...", "Cluster: ...", "3D space selection" — see each caller in
// ThemeAccordion.tsx/IdeaRow.tsx/SearchResultsWithStudyGuide.tsx/
// VectorSpaceLegend.tsx/VectorSpaceView.tsx/BoardDetail.tsx. That label is
// the only source-of-truth for what a collection was generated from — there
// is deliberately no separate machine-readable "type" column alongside it
// (tried that, it was pure redundancy: every caller that would set it
// already sets a label with a parseable prefix, so it never carried
// information the label didn't). Bucketing is many-to-one on purpose —
// Theme/Idea/Cluster all read as the same "system-detected grouping"
// concept and share one color.
function inferSourceType(label: string | null): NonNullSourceType | null {
  if (!label) return null;
  if (/^Board:/.test(label)) return "board";
  if (/^Search:/.test(label)) return "search";
  if (/^(Theme|Idea|Cluster):/.test(label)) return "cluster";
  if (/^3D space selection/.test(label)) return "manual";
  return null;
}

/** The fixed TapeColor for a collection's card on the /study-guides
 * corkboard — one of exactly five colors, never random: the color for the
 * type inferred from source_label's prefix, or UNLABELED_TAPE_COLOR if
 * nothing matches. */
export function tapeColorForSourceLabel(sourceLabel: string | null): TapeColor {
  const resolved = inferSourceType(sourceLabel);
  return resolved ? SOURCE_TYPE_TAPE_COLORS[resolved] : UNLABELED_TAPE_COLOR;
}
