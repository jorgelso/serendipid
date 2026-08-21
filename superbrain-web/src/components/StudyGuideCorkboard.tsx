"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import type { StudyGuide, StudyGuideCollection } from "@/types/domain";
import { makeRng, pick, seededRotation, seededTapeColor } from "@/lib/collage";
import WashiTape from "./WashiTape";
import PushPin from "./PushPin";
import TornPhoto from "./TornPhoto";
import PaperTicket from "./PaperTicket";
import StickerLabel from "./StickerLabel";
import DeleteStudyGuideCollectionButton from "./DeleteStudyGuideCollectionButton";

const POLL_MS = 3000;
const CANVAS_W = 1200;
const SCATTER_COUNT = 70;

// Found-object illustrations, not reel photography — a talking-head video
// frame reads as "an app screenshot" no matter how it's graded, so the
// collage's photographic material is now this curated set of stock
// illustrations/objects (the actual reference collages are built almost
// entirely from material like this) instead of the guide's source posts.
// "line" items are dark ink/line art on transparent — they read fine as-is
// on this app's light theme, but need inverting to read as light etching
// once the page goes dark, so their filter comes from the theme-aware
// --ill-line-filter token (globals.css) rather than a literal value here.
// "photo" items (vinyl, key, flowers, car) already carry their own color in
// both themes and only get a small edge-visibility boost (--ill-photo-filter).
const ILLUSTRATIONS = [
  { src: "/collage/vinyl.png", kind: "photo", aspect: 1 },
  { src: "/collage/camera.png", kind: "line", aspect: 1936 / 2311 },
  { src: "/collage/key.png", kind: "photo", aspect: 391 / 115 },
  { src: "/collage/rose.png", kind: "line", aspect: 508 / 800 },
  { src: "/collage/cat.png", kind: "line", aspect: 393 / 501 },
  { src: "/collage/spiderweb.png", kind: "line", aspect: 316 / 400 },
  { src: "/collage/guitar.png", kind: "line", aspect: 2308 / 908 },
  { src: "/collage/flowers.png", kind: "photo", aspect: 1140 / 1280 },
  { src: "/collage/car.png", kind: "photo", aspect: 958 / 568 },
] as const;

function illustrationFilter(kind: "line" | "photo"): string {
  return kind === "line" ? "var(--ill-line-filter)" : "var(--ill-photo-filter)";
}

// A drawn star silhouette (not a Unicode "★" glyph) — a real die-cut shape
// with its own drop shadow, standing in for the found paper-sticker stars
// the reference collages use, since a flat text character reads as UI
// chrome, not a physical sticker.
function StarSticker({ left, top, size, rot, z, color }: { left: number; top: number; size: number; rot: number; z: number; color: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className="absolute"
      style={{ left, top, transform: `rotate(${rot}deg)`, zIndex: z, filter: "drop-shadow(0 4px 7px rgba(0,0,0,.5))" }}
      aria-hidden
    >
      <path
        d="M50 2 L61 37 L98 37 L68 59 L79 95 L50 73 L21 95 L32 59 L2 37 L39 37 Z"
        fill={color}
        stroke="rgba(0,0,0,.25)"
        strokeWidth="2"
      />
    </svg>
  );
}

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

// Section headers pulled straight out of the guide's own markdown ("## ...")
// — used as scattered "clipping" tickets in the scatter fill, so the loose
// text fragments are real content, not lorem-ish filler.
function extractHeaders(content: string | undefined): string[] {
  if (!content) return [];
  const matches = [...content.matchAll(/^##\s+(.+)$/gm)].map((m) => m[1].trim());
  return matches.slice(0, 10);
}

// The first sentence of each bullet in the guide's markdown, stripped of
// markdown/citation noise — real, punchy, sentence-length lines straight out
// of the guide's own content ("Turn vague aspirations into observable
// actions.") to use as the collage's dominant "found text" clipping
// material, the way a real collage leans on printed phrases (not just
// photography) for most of its density.
function extractQuotes(content: string | undefined): string[] {
  if (!content) return [];
  const lines = [...content.matchAll(/^-\s+(.+)$/gm)].map((m) => m[1]);
  const quotes = lines
    .map((l) =>
      l
        .replace(/\*\*/g, "")
        .replace(/\[\d+\](?:,\s*\[\d+\])*/g, "")
        .replace(/\([^)]*\)/g, "")
        .trim(),
    )
    .map((l) => l.split(/(?<=[.!?])\s/)[0])
    .filter((s) => s.length >= 20 && s.length <= 80);
  return [...new Set(quotes)].slice(0, 30);
}

// "Cluster: \"#personalfinance\"" -> "#PERSONALFINANCE" — a short, punchy
// fragment for the foil headline chip, pulled from real data rather than
// a hand-picked word (which only works for one-off demo content).
function foilLabel(collection: StudyGuideCollection): string {
  const hashtag = collection.source_label?.match(/#\w+/)?.[0];
  if (hashtag) return hashtag.toUpperCase();
  return (collection.source_label ?? "GUIDE").slice(0, 16).toUpperCase();
}

function splitTitle(title: string): { headline: string; rest: string } {
  const words = title.replace(/[:"']/g, "").split(/\s+/).filter(Boolean);
  return { headline: (words[0] ?? "Guide").toUpperCase(), rest: words.slice(1).join(" ") };
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

const ACCENTS = ["coral", "yellow", "teal", "lavender", "mint", "rose", "sky"] as const;

function CollageCluster({ collection }: { collection: StudyGuideCollection }) {
  const finalGuide = collection.guides.find((g) => g.role === "final");
  const others = collection.guides.filter((g) => g.id !== finalGuide?.id);
  const sourceGuide = finalGuide ?? collection.guides[0];
  const headers = extractHeaders(sourceGuide?.content);
  const quotes = extractQuotes(sourceGuide?.content);
  const title = finalGuide?.title ?? collection.source_label ?? "Untitled guide";
  const { headline, rest } = splitTitle(title);
  const foil = foilLabel(collection);
  const tapeColor = seededTapeColor(collection.id + 3);

  const height = 1220;

  // Material mix, deliberately text-dominant: real *text* clippings pulled
  // from the guide's own content, plus found-object illustrations, not
  // photography — see the ILLUSTRATIONS comment above for why reel photos
  // are excluded entirely now.
  const rng = makeRng(collection.id);
  const scatter: ReactNode[] = [];
  if (headers.length > 0 || quotes.length > 0) {
    for (let i = 0; i < SCATTER_COUNT; i++) {
      const x = Math.round(rng() * (CANVAS_W - 40) - 30);
      const y = Math.round(rng() * (height - 80) + 20);
      const rot = Math.round((rng() * 2 - 1) * 14 * 10) / 10;
      const z = 1 + Math.floor(rng() * 8);
      const roll = rng();
      if (roll < 0.2) {
        const ill = pick(rng, ILLUSTRATIONS);
        const w = Math.round(55 + rng() * 70);
        scatter.push(
          <span key={`i${i}`} className="absolute" style={{ left: x, top: y, width: w, transform: `rotate(${rot}deg)`, zIndex: z }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={ill.src}
              alt=""
              className="block w-full"
              style={{ filter: `${illustrationFilter(ill.kind)} drop-shadow(0 8px 14px rgba(0,0,0,.5))`, aspectRatio: ill.aspect }}
            />
          </span>,
        );
      } else if (roll < 0.55 && quotes.length > 0) {
        const text = pick(rng, quotes);
        const w = Math.round(170 + rng() * 90);
        const stock = pick(rng, ["strip", "notebook", "note"] as const);
        scatter.push(
          <PaperTicket key={`q${i}`} kind="quote" stock={stock} left={x} top={y} width={w} fontSize={14} rotation={rot} z={z} color="#1c1508">
            {text}
          </PaperTicket>,
        );
      } else if (roll < 0.68 && headers.length > 0) {
        const text = pick(rng, headers);
        const w = Math.round(130 + rng() * 50);
        scatter.push(
          <PaperTicket key={`t${i}`} kind="type" left={x} top={y} width={w} fontSize={10} rotation={rot} z={z} color="#221a12">
            {text}
          </PaperTicket>,
        );
      } else if (roll < 0.78) {
        const accent = pick(rng, ACCENTS);
        const size = Math.round(45 + rng() * 45);
        scatter.push(
          <div
            key={`s${i}`}
            className="absolute"
            style={{
              left: x,
              top: y,
              width: size,
              height: Math.round(size * 0.6),
              transform: `rotate(${rot}deg)`,
              zIndex: z,
              WebkitMaskImage: "url(/collage/torn-note.png)",
              maskImage: "url(/collage/torn-note.png)",
              WebkitMaskSize: "100% 100%",
              maskSize: "100% 100%",
              WebkitMaskRepeat: "no-repeat",
              maskRepeat: "no-repeat",
              backgroundColor: `var(--color-${accent}-soft)`,
              filter: "drop-shadow(0 6px 10px rgba(0,0,0,.4))",
            }}
          />,
        );
      } else if (roll < 0.86) {
        const accent = pick(rng, ACCENTS);
        const size = Math.round(60 + rng() * 40);
        scatter.push(
          <div
            key={`k${i}`}
            className="absolute"
            style={{
              left: x,
              top: y,
              width: size,
              height: Math.round(size * 0.46),
              transform: `rotate(${rot}deg)`,
              zIndex: z,
              WebkitMaskImage: "url(/collage/ticket-shape.png)",
              maskImage: "url(/collage/ticket-shape.png)",
              WebkitMaskSize: "100% 100%",
              maskSize: "100% 100%",
              WebkitMaskRepeat: "no-repeat",
              maskRepeat: "no-repeat",
              backgroundColor: `var(--color-${accent}-ink)`,
              filter: "drop-shadow(0 6px 10px rgba(0,0,0,.4))",
            }}
          />,
        );
      } else if (roll < 0.93) {
        const accent = pick(rng, ACCENTS);
        scatter.push(
          <StarSticker key={`st${i}`} left={x} top={y} size={Math.round(20 + rng() * 20)} rot={rot} z={z} color={`var(--color-${accent}-ink)`} />,
        );
      } else {
        const w = Math.round(44 + rng() * 18);
        scatter.push(
          <span
            key={`tp${i}`}
            className="absolute"
            style={{ left: x, top: y, width: w, transform: `rotate(${rot}deg)`, zIndex: 45 }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/collage/tape.png" alt="" className="block w-full drop-shadow-[0_3px_5px_rgba(0,0,0,0.4)]" />
          </span>
        );
      }
    }
  }

  return (
    <div className="relative mb-10 overflow-x-auto">
      <div className="relative" style={{ width: CANVAS_W, height, minWidth: CANVAS_W }}>
        {scatter}

        {/* hero: the actual generated guide, always on top of the scatter fill */}
        {finalGuide ? (
          <Link href={`/study-guides/${finalGuide.id}`} className="absolute" style={{ left: 460, top: 16, zIndex: 20 }}>
            <TornPhoto
              src={`/api/study-guides/${finalGuide.id}/thumbnail`}
              alt={finalGuide.title ?? "Study guide"}
              seed={collection.id + 7}
              frame="torn"
              width={310}
              height={440}
              rotation={-4}
              z={20}
              left={0}
              top={0}
              className="shadow-[0_20px_34px_-12px_rgba(0,0,0,0.7)]"
            />
          </Link>
        ) : (
          <div
            style={{
              position: "absolute",
              left: 460,
              top: 16,
              width: 310,
              height: 440,
              transform: `rotate(${seededRotation(collection.id, 5)}deg)`,
              zIndex: 20,
            }}
            className="border-line bg-surface-2 font-hand text-ink-muted flex items-center justify-center rounded-sm border border-dashed text-center text-sm"
          >
            scribbling…
          </div>
        )}
        {/* A real vinyl-record photo, used once per cluster (not scattered)
            — the references lean on a handful of singular found-object
            photos like this rather than repeating one material everywhere. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/collage/vinyl.png"
          alt=""
          aria-hidden
          className="absolute"
          style={{ left: 1040, top: 160, width: 130, transform: "rotate(8deg)", zIndex: 8, filter: "var(--ill-photo-filter) drop-shadow(0 14px 22px rgba(0,0,0,.55))" }}
        />
        {/* A vintage camera line-art illustration — a second singular found
            object (not tied to the reel content at all). Its filter comes
            from the theme-aware --ill-line-filter token: natural dark ink on
            the light page, inverted to light ink once the page goes dark. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/collage/camera.png"
          alt=""
          aria-hidden
          className="absolute"
          style={{
            left: 60,
            top: 940,
            width: 100,
            transform: "rotate(-6deg)",
            zIndex: 29,
            filter: "var(--ill-line-filter) drop-shadow(0 10px 16px rgba(0,0,0,.5))",
          }}
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/collage/key.png"
          alt=""
          aria-hidden
          className="absolute"
          style={{ left: 830, top: 20, width: 150, transform: "rotate(-18deg)", zIndex: 18, filter: "var(--ill-photo-filter) drop-shadow(0 10px 16px rgba(0,0,0,.5))" }}
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/collage/rose.png"
          alt=""
          aria-hidden
          className="absolute"
          style={{
            left: 800,
            top: 380,
            width: 120,
            transform: "rotate(9deg)",
            zIndex: 21,
            filter: "var(--ill-line-filter) drop-shadow(0 10px 16px rgba(0,0,0,.5))",
          }}
        />

        {/* Zero-size anchors — PushPin/WashiTape position themselves via
            left-1/2 relative to their direct parent, so each gets its own
            anchor at the hero photo's top-center rather than the whole
            1200px-wide canvas' center. */}
        <div className="absolute" style={{ left: 615, top: 16, zIndex: 27 }}>
          <PushPin color={`var(--color-${seededTapeColor(collection.id)})`} />
        </div>
        <div className="absolute" style={{ left: 615, top: -6, zIndex: 25 }}>
          <WashiTape color={tapeColor} rotation={seededRotation(collection.id + 3, 10)} />
        </div>

        {/* ==== title, cut from real paper ==== */}
        <PaperTicket kind="mag" left={30} top={640} width={320} height={112} fontSize={58} color="#161207" maskColor="var(--color-yellow)" rotation={-6} z={33}>
          {headline}
        </PaperTicket>
        <PaperTicket kind="foil" left={360} top={676} width={230} height={84} fontSize={38} rotation={4} z={34}>
          {foil}
        </PaperTicket>
        {rest && (
          <PaperTicket kind="script" left={30} top={760} width={360} fontSize={30} color="#7a2418" rotation={-2} z={36}>
            {rest}
          </PaperTicket>
        )}
        <PaperTicket kind="type" left={50} top={900} width={210} fontSize={11} color="#221a12" rotation={-3} z={32}>
          {collection.source_label ?? "Study guide"} · {new Date(collection.created_at).toLocaleDateString()}
        </PaperTicket>
        {others.length > 0 && (
          <details className="absolute" style={{ left: 300, top: 895, zIndex: 38 }}>
            <summary className="[&::-webkit-details-marker]:hidden list-none cursor-pointer select-none">
              <span
                className="font-hand inline-block rounded-[3px] px-2 py-1 text-[13px] font-bold"
                style={{ backgroundColor: "var(--paper-bg)", color: "#221a12", transform: "rotate(-3deg)", boxShadow: "0 4px 8px rgba(0,0,0,.4)" }}
              >
                +{others.length} more guides
              </span>
            </summary>
            <div style={{ backgroundColor: "var(--paper-bg)" }} className="mt-2 flex max-w-[240px] flex-wrap gap-2 rounded-sm p-2 shadow-[0_10px_20px_-10px_rgba(0,0,0,0.5)]">
              {others.map((g) => (
                <Link key={g.id} href={`/study-guides/${g.id}`} className="font-hand text-ink-muted hover:text-coral-ink text-xs">
                  {roleLabel(g, collection.guides)}
                </Link>
              ))}
            </div>
          </details>
        )}

        {collection.status !== "complete" && (
          <div className="absolute" style={{ left: 20, top: 900, zIndex: 39 }}>
            <StatusNote collection={collection} />
          </div>
        )}

        <div className="absolute opacity-60 transition-opacity hover:opacity-100" style={{ left: CANVAS_W - 40, top: 8, zIndex: 50 }}>
          <DeleteStudyGuideCollectionButton id={collection.id} guideCount={collection.guides.length} />
        </div>
      </div>
    </div>
  );
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
    <div className="relative">
      {collections.map((collection) => (
        <CollageCluster key={collection.id} collection={collection} />
      ))}
    </div>
  );
}
