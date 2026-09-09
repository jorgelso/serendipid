import WashiTape from "./WashiTape";
import {
  NON_NULL_SOURCE_TYPES,
  SOURCE_TYPE_LABELS,
  SOURCE_TYPE_TAPE_COLORS,
  UNLABELED_TAPE_COLOR,
} from "@/lib/studyGuideSource";

// A small sticky note explaining the corkboard's title-chip color coding by
// what a collection was generated from (parsed from source_label's prefix,
// see studyGuideSource.ts) — same paper/tape/hand-lettering primitives as
// ScrapbookMasthead's subtitle note, so it reads as another scrap pinned to
// the board rather than a UI legend widget bolted on top of the scrapbook.
// Swatches read straight off SOURCE_TYPE_TAPE_COLORS (studyGuideSource.ts) —
// the exact same lookup StudyGuideCorkboard.tsx feeds into CutoutChip's
// `color` override, so this can never silently drift out of sync with what
// a title chip actually renders.
export default function StudyGuideSourceLegend() {
  return (
    <div
      style={{ transform: "rotate(-2.5deg)", backgroundColor: "var(--paper-bg)" }}
      className="border-line relative w-fit rounded-[2px] border px-4 py-3 shadow-[0_8px_16px_-8px_rgba(0,0,0,0.4)]"
    >
      <WashiTape color="yellow" rotation={7} />
      <p className="font-hand text-ink mb-2 text-sm font-bold">the title color means…</p>
      <div className="flex flex-col gap-1.5">
        {NON_NULL_SOURCE_TYPES.map((type) => {
          const tapeColor = SOURCE_TYPE_TAPE_COLORS[type];
          return (
            <div key={type} className="flex items-center gap-2">
              <span
                aria-hidden
                style={{
                  backgroundColor: `var(--color-${tapeColor}-soft)`,
                  color: `var(--color-${tapeColor}-ink)`,
                  borderColor: `var(--color-${tapeColor}-ink)`,
                }}
                className="font-display flex h-5 w-5 shrink-0 items-center justify-center rounded-[3px] border text-[11px] font-bold"
              >
                Aa
              </span>
              <span className="font-hand text-ink-muted text-sm">{SOURCE_TYPE_LABELS[type]}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            style={{
              backgroundColor: `var(--color-${UNLABELED_TAPE_COLOR}-soft)`,
              color: `var(--color-${UNLABELED_TAPE_COLOR}-ink)`,
              borderColor: `var(--color-${UNLABELED_TAPE_COLOR}-ink)`,
            }}
            className="font-display flex h-5 w-5 shrink-0 items-center justify-center rounded-[3px] border text-[11px] font-bold"
          >
            ?
          </span>
          <span className="font-hand text-ink-muted text-sm">Older / unlabeled</span>
        </div>
      </div>
    </div>
  );
}
