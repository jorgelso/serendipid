"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { StudyGuide, StudyGuideCollection } from "@/types/domain";
import { seededRotation, seededTapeColor, seededOffset, seededZIndex } from "@/lib/collage";
import WashiTape from "./WashiTape";
import PushPin from "./PushPin";
import PolaroidThumb from "./PolaroidThumb";
import CutoutChip from "./CutoutChip";
import TypewriterTag from "./TypewriterTag";
import StickerLabel from "./StickerLabel";
import DeleteStudyGuideCollectionButton from "./DeleteStudyGuideCollectionButton";

const POLL_MS = 3000;

const ROLE_LABEL: Record<string, string> = {
  final: "Final",
  full: "Full pass",
  merge: "Merged",
  chunk: "Chunk",
};

function roleLabel(guide: StudyGuide, guides: StudyGuide[]): string {
  if (guide.role !== "chunk") return ROLE_LABEL[guide.role] ?? guide.role;
  const chunkIndex = guides.filter((g) => g.role === "chunk").findIndex((g) => g.id === guide.id);
  return `Chunk ${chunkIndex + 1}`;
}

function StatusNote({ collection }: { collection: StudyGuideCollection }) {
  switch (collection.status) {
    case "generating":
      return (
        <StickerLabel color="coral" rotation={-3}>
          ✏️ still sketching…{" "}
          {collection.expected_guide_count
            ? `(${collection.guides.length}/${collection.expected_guide_count})`
            : `(${collection.guides.length} so far)`}
        </StickerLabel>
      );
    case "interrupted":
      return (
        <StickerLabel color="yellow" rotation={-3}>
          ⚠ interrupted — {collection.guides.length} kept
        </StickerLabel>
      );
    case "failed":
      return (
        <StickerLabel color="rose" rotation={-3}>
          ✗ didn&rsquo;t finish
        </StickerLabel>
      );
    default:
      return null;
  }
}

// Fan positions for sibling thumbnails peeking out from behind the main
// photo — deterministic per collection+index (not Math.random()) so the
// pile doesn't jitter while this component polls a still-generating
// collection every few seconds.
function fanOffset(seed: number, i: number) {
  const s = seed + i * 13;
  const side = i % 2 === 0 ? 1 : -1;
  return {
    top: 30 + i * 22 + seededOffset(s, 10),
    left: side * (16 + i * 18) + seededOffset(s + 1, 8),
    rotate: seededRotation(s + 2, 16),
    z: seededZIndex(s + 3, 1, 4),
  };
}

export default function StudyGuideCorkboard({ initialCollections }: { initialCollections: StudyGuideCollection[] }) {
  const [collections, setCollections] = useState(initialCollections);

  useEffect(() => {
    if (!collections.some((c) => c.status === "generating")) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/study-guide-collections");
        if (!res.ok) return;
        const data = await res.json();
        setCollections(data.data);
      } catch {
        // Transient network hiccup — just try again next tick.
      }
    }, POLL_MS);
    return () => clearInterval(interval);
  }, [collections]);

  if (collections.length === 0) {
    return (
      <p className="font-hand text-ink-muted py-16 text-center text-lg">
        Nothing pinned up yet — select posts, or generate one from a theme, idea, or 3D-space cluster.
      </p>
    );
  }

  return (
    <div className="relative columns-1 gap-x-2 sm:columns-2 lg:columns-3 xl:columns-4">
      {collections.map((collection, i) => {
        const finalGuide = collection.guides.find((g) => g.role === "final");
        const others = collection.guides.filter((g) => g.id !== finalGuide?.id);
        const fanned = others.slice(0, 3);
        const overflow = others.slice(3);
        const tapeColor = seededTapeColor(collection.id + 3);
        // Staggered vertical + horizontal offset by index parity — breaks
        // the columns layout's tidy top-aligned rhythm so piles read as a
        // scattered spread, and negative bottom margin lets consecutive
        // piles in a column crowd/overlap rather than sit in clean rows.
        const stagger = ["4px", "58px", "26px", "42px"][i % 4];

        return (
          <div
            key={collection.id}
            style={{ marginTop: stagger, marginLeft: i % 2 === 0 ? "0px" : "14px", zIndex: seededZIndex(collection.id, 1, 5) }}
            className="group relative mb-[-8px] break-inside-avoid pt-9 pr-7 pb-11 pl-2"
          >
            {/* Fanned-out siblings, tucked behind the main photo */}
            {fanned.map((g, gi) => {
              const f = fanOffset(collection.id, gi);
              return (
                <Link
                  key={g.id}
                  href={`/study-guides/${g.id}`}
                  className="absolute"
                  style={{ top: `${f.top}px`, left: `${f.left}px`, zIndex: f.z }}
                >
                  <PolaroidThumb
                    src={`/api/study-guides/${g.id}/thumbnail`}
                    alt={g.title ?? "Study guide"}
                    seed={g.id}
                    rotation={f.rotate}
                    caption={roleLabel(g, collection.guides)}
                    size="sm"
                  />
                </Link>
              );
            })}

            {/* Main photo — the only normal-flow element, so it's what sets the pile's footprint */}
            <div className="relative inline-block" style={{ zIndex: 10 }}>
              {finalGuide ? (
                <Link href={`/study-guides/${finalGuide.id}`} className="block">
                  <PolaroidThumb
                    src={`/api/study-guides/${finalGuide.id}/thumbnail`}
                    alt={finalGuide.title ?? "Study guide"}
                    seed={finalGuide.id}
                    size="lg"
                  />
                </Link>
              ) : (
                <div
                  style={{ transform: `rotate(${seededRotation(collection.id, 5)}deg)` }}
                  className="border-line bg-surface-2 font-hand text-ink-muted flex h-48 w-36 items-center justify-center rounded-sm border border-dashed text-center text-xs"
                >
                  scribbling…
                </div>
              )}

              <PushPin color={`var(--color-${seededTapeColor(collection.id)})`} />
              <WashiTape color={tapeColor} rotation={seededRotation(collection.id + 3, 10)} />
            </div>

            {/* Title — a magazine-cutout chip pasted across the photo's top-left corner, not a caption underneath it */}
            <div
              className="absolute max-w-[82%]"
              style={{
                top: `${-10 - seededOffset(collection.id + 5, 6)}px`,
                left: `${-6 + seededOffset(collection.id + 6, 10)}px`,
                zIndex: 20,
              }}
            >
              <CutoutChip seed={collection.id + 7} size="md" rotationRange={6} className="line-clamp-2">
                {finalGuide?.title ?? collection.source_label ?? "Untitled pile of reels"}
              </CutoutChip>
            </div>

            {/* Metadata — a typewritten strip overlapping the photo's bottom edge */}
            <div
              className="absolute"
              style={{
                bottom: `${-6 + seededOffset(collection.id + 9, 6)}px`,
                left: `${6 + seededOffset(collection.id + 10, 12)}px`,
                zIndex: 20,
              }}
            >
              <TypewriterTag rotation={seededRotation(collection.id + 9, 6)}>
                {collection.source_label ?? "Study guide"} · {new Date(collection.created_at).toLocaleDateString()}
              </TypewriterTag>
            </div>

            {/* Status sticker — pinned near the top-right corner, only when there's something to flag */}
            {collection.status !== "complete" && (
              <div className="absolute" style={{ top: "4px", right: "-14px", zIndex: 21 }}>
                <StatusNote collection={collection} />
              </div>
            )}

            {/* Overflow drawer — only surfaces when siblings run past what fits fanned out */}
            {overflow.length > 0 && (
              <details className="absolute" style={{ bottom: "-6px", right: "-8px", zIndex: 22 }}>
                <summary className="[&::-webkit-details-marker]:hidden list-none">
                  <StickerLabel color={tapeColor} rotation={4} className="cursor-pointer select-none">
                    +{overflow.length} more
                  </StickerLabel>
                </summary>
                <div
                  style={{ backgroundColor: "var(--paper-bg)" }}
                  className="mt-2 flex max-w-[220px] flex-wrap justify-end gap-2 rounded-sm p-2 shadow-[0_10px_20px_-10px_rgba(0,0,0,0.5)]"
                >
                  {overflow.map((g) => (
                    <Link key={g.id} href={`/study-guides/${g.id}`}>
                      <PolaroidThumb
                        src={`/api/study-guides/${g.id}/thumbnail`}
                        alt={g.title ?? "Study guide"}
                        seed={g.id}
                        caption={roleLabel(g, collection.guides)}
                        size="sm"
                      />
                    </Link>
                  ))}
                </div>
              </details>
            )}

            <div
              className="absolute opacity-0 transition-opacity group-hover:opacity-100"
              style={{ top: "0px", right: "-2px", zIndex: 30 }}
            >
              <DeleteStudyGuideCollectionButton id={collection.id} guideCount={collection.guides.length} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
