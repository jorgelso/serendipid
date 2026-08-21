"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import type { StudyGuide, StudyGuideCollection } from "@/types/domain";
import { seededRotation, seededTapeColor } from "@/lib/collage";
import PaperCutout from "./PaperCutout";
import WashiTape from "./WashiTape";
import PushPin from "./PushPin";
import PolaroidThumb from "./PolaroidThumb";
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

// A small die-cut "sticker" label — used for the recurring status/role
// callouts so they read as taped-on ephemera rather than a plain UI badge.
function StickerLabel({ children, color, rotation }: { children: ReactNode; color: string; rotation: number }) {
  return (
    <span
      style={{ transform: `rotate(${rotation}deg)`, backgroundColor: `var(--color-${color}-soft)`, color: `var(--color-${color}-ink)` }}
      className="font-hand inline-block rounded-[3px] px-2 py-0.5 text-[13px] font-bold leading-none shadow-[0_2px_4px_rgba(0,0,0,0.25)]"
    >
      {children}
    </span>
  );
}

function StatusNote({ collection }: { collection: StudyGuideCollection }) {
  switch (collection.status) {
    case "generating":
      return (
        <StickerLabel color="coral" rotation={-2}>
          ✏️ still sketching…{" "}
          {collection.expected_guide_count
            ? `(${collection.guides.length}/${collection.expected_guide_count})`
            : `(${collection.guides.length} so far)`}
        </StickerLabel>
      );
    case "interrupted":
      return (
        <StickerLabel color="yellow" rotation={-2}>
          ⚠ interrupted — {collection.guides.length} kept
        </StickerLabel>
      );
    case "failed":
      return (
        <StickerLabel color="rose" rotation={-2}>
          ✗ didn&rsquo;t finish
        </StickerLabel>
      );
    default:
      return null;
  }
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
    <div className="relative columns-1 gap-x-8 sm:columns-2 lg:columns-3">
      {collections.map((collection, i) => {
        const finalGuide = collection.guides.find((g) => g.role === "final");
        const others = collection.guides.filter((g) => g.id !== finalGuide?.id);
        // Staggered vertical offset by index parity — breaks the columns
        // layout's tidy top-aligned rhythm so pieces read as scattered
        // rather than gridded, closer to a real spread than a card grid.
        const stagger = ["0px", "34px", "16px"][i % 3];
        return (
          <div key={collection.id} style={{ marginTop: stagger }} className="relative z-10 mb-10 break-inside-avoid pt-3">
            <PushPin color={`var(--color-${seededTapeColor(collection.id)})`} />
              <PaperCutout seed={collection.id} rotationRange={4} className="px-5 pt-6 pb-4 shadow-[0_14px_26px_-18px_rgba(0,0,0,0.5)]">
                <WashiTape color={seededTapeColor(collection.id + 3)} rotation={seededRotation(collection.id + 3, 10)} />

                <p className="font-hand text-xl leading-tight">
                  {finalGuide?.title ?? collection.source_label ?? "Untitled pile of reels"}
                </p>
                <p className="text-ink-muted mt-1 text-[11px] font-bold tracking-wide uppercase">
                  {collection.source_label ?? "Study guide"} · {new Date(collection.created_at).toLocaleDateString()}
                </p>
                <div className="mt-2">
                  <StatusNote collection={collection} />
                </div>

                <div className="mt-4">
                  {finalGuide ? (
                    <Link href={`/study-guides/${finalGuide.id}`} className="inline-block">
                      <PolaroidThumb src={`/api/study-guides/${finalGuide.id}/thumbnail`} alt={finalGuide.title ?? "Study guide"} seed={finalGuide.id} />
                    </Link>
                  ) : (
                    <div className="border-line bg-surface-2 font-hand text-ink-muted flex h-36 w-28 items-center justify-center rounded-sm border border-dashed text-center text-xs">
                      scribbling…
                    </div>
                  )}
                </div>

                {others.length > 0 && (
                  <details className="mt-4">
                    <summary className="font-hand text-coral-ink cursor-pointer text-sm select-none">
                      + {others.length} more taped up here
                    </summary>
                    <div className="mt-3 flex flex-wrap gap-3">
                      {others.map((g) => (
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

                <div className="mt-4 flex justify-end">
                  <DeleteStudyGuideCollectionButton id={collection.id} guideCount={collection.guides.length} />
                </div>
              </PaperCutout>
          </div>
        );
      })}
    </div>
  );
}
