"use client";

import type { ReactNode } from "react";
import WashiTape from "./WashiTape";
import type { TapeColor } from "@/lib/collage";

// A wide, varied set of hand-drawn-style marks scattered across the WHOLE
// page as background ephemera — not confined to one component's box. Mix
// of doodle glyphs and small drawn squiggle/scribble SVGs so it doesn't
// read as one repeated icon. Position/rotation/size are fixed per-index
// (not randomized per render) so the page doesn't jitter while
// StudyGuideCorkboard polls a still-generating collection above it.
const EPHEMERA: { top: string; left: string; rot: number; size: string; glyph: string; opacity: number }[] = [
  { top: "3%", left: "6%", rot: -14, size: "text-4xl", glyph: "✦", opacity: 0.3 },
  { top: "2%", left: "88%", rot: 10, size: "text-3xl", glyph: "✂", opacity: 0.28 },
  { top: "9%", left: "48%", rot: 6, size: "text-2xl", glyph: "❤", opacity: 0.22 },
  { top: "16%", left: "22%", rot: -8, size: "text-xl", glyph: "★", opacity: 0.25 },
  { top: "13%", left: "95%", rot: 16, size: "text-2xl", glyph: "✎", opacity: 0.28 },
  { top: "27%", left: "3%", rot: 12, size: "text-3xl", glyph: "✦", opacity: 0.24 },
  { top: "24%", left: "70%", rot: -10, size: "text-xl", glyph: "✱", opacity: 0.22 },
  { top: "38%", left: "92%", rot: -6, size: "text-2xl", glyph: "★", opacity: 0.24 },
  { top: "42%", left: "12%", rot: 18, size: "text-xl", glyph: "❤", opacity: 0.2 },
  { top: "52%", left: "55%", rot: -12, size: "text-2xl", glyph: "✂", opacity: 0.22 },
  { top: "58%", left: "4%", rot: 8, size: "text-2xl", glyph: "✦", opacity: 0.26 },
  { top: "63%", left: "96%", rot: -16, size: "text-3xl", glyph: "✱", opacity: 0.24 },
  { top: "72%", left: "30%", rot: 10, size: "text-xl", glyph: "★", opacity: 0.2 },
  { top: "78%", left: "88%", rot: -8, size: "text-2xl", glyph: "✎", opacity: 0.24 },
  { top: "85%", left: "8%", rot: 14, size: "text-3xl", glyph: "✦", opacity: 0.26 },
  { top: "92%", left: "60%", rot: -10, size: "text-xl", glyph: "❤", opacity: 0.2 },
  { top: "95%", left: "40%", rot: 6, size: "text-2xl", glyph: "★", opacity: 0.22 },
  // Extra pass — pushes density up further so the base layer itself reads
  // as cluttered/collaged rather than a sparse plain backdrop.
  { top: "6%", left: "32%", rot: 20, size: "text-xl", glyph: "✂", opacity: 0.2 },
  { top: "11%", left: "65%", rot: -18, size: "text-2xl", glyph: "✦", opacity: 0.22 },
  { top: "20%", left: "10%", rot: 9, size: "text-lg", glyph: "✱", opacity: 0.2 },
  { top: "33%", left: "48%", rot: -6, size: "text-xl", glyph: "❤", opacity: 0.18 },
  { top: "36%", left: "82%", rot: 14, size: "text-lg", glyph: "★", opacity: 0.2 },
  { top: "48%", left: "24%", rot: -20, size: "text-2xl", glyph: "✎", opacity: 0.2 },
  { top: "55%", left: "70%", rot: 8, size: "text-xl", glyph: "✂", opacity: 0.2 },
  { top: "66%", left: "45%", rot: -9, size: "text-lg", glyph: "✱", opacity: 0.18 },
  { top: "75%", left: "60%", rot: 16, size: "text-2xl", glyph: "✦", opacity: 0.22 },
  { top: "82%", left: "20%", rot: -12, size: "text-xl", glyph: "❤", opacity: 0.18 },
  { top: "88%", left: "78%", rot: 6, size: "text-lg", glyph: "★", opacity: 0.2 },
];

// A handful of loose, unattached tape scraps left lying on the page itself
// (not pinning anything down) — more "found material" clutter so the base
// layer reads as a messy pile before any content cards land on top of it.
const TAPE_SCRAPS: { top: string; left: string; rot: number; color: TapeColor }[] = [
  { top: "5%", left: "18%", rot: -30, color: "teal" },
  { top: "17%", left: "76%", rot: 24, color: "rose" },
  { top: "44%", left: "6%", rot: 40, color: "sky" },
  { top: "61%", left: "88%", rot: -20, color: "mint" },
  { top: "80%", left: "40%", rot: 18, color: "lavender" },
];

// A couple of long, loose hand-drawn squiggle strokes (SVG, not glyphs) for
// variety against the repeated star/heart marks above.
function Squiggle({ top, left, rot, width = 90 }: { top: string; left: string; rot: number; width?: number }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 100 20"
      width={width}
      style={{ position: "absolute", top, left, transform: `rotate(${rot}deg)` }}
      className="text-ink-muted/25"
    >
      <path
        d="M2 10 Q 15 2, 28 10 T 54 10 T 80 10 T 98 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Full-page decorative layer, sitting behind real content (z-0) so cards
// and text render on top of it while still reading as "scattered around
// and between" the pieces, the way loose ephemera sits on a physical
// scrapbook spread. Purely atmospheric — aria-hidden, pointer-events-none.
function PageEphemera() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {EPHEMERA.map((e, i) => (
        <span
          key={i}
          style={{ top: e.top, left: e.left, transform: `rotate(${e.rot}deg)`, opacity: e.opacity }}
          className={`font-hand text-ink absolute select-none ${e.size}`}
        >
          {e.glyph}
        </span>
      ))}
      <Squiggle top="20%" left="40%" rot={-4} width={110} />
      <Squiggle top="68%" left="18%" rot={8} width={130} />
      <Squiggle top="46%" left="80%" rot={-10} width={90} />

      {TAPE_SCRAPS.map((t, i) => (
        // WashiTape positions itself relative to its own parent (left-1/2,
        // -top-3), so each scrap gets its own zero-size anchor at the
        // scattered page coordinate rather than being placed directly.
        <div key={i} className="absolute" style={{ top: t.top, left: t.left }}>
          <WashiTape color={t.color} rotation={t.rot} className="opacity-70" />
        </div>
      ))}
    </div>
  );
}

// The full-bleed "scrapbook spread" surface for the whole /study-guides
// page — NOT one bordered box holding tidy cards, the entire page below
// the header is the textured page, with ephemera scattered across all of
// it and content (masthead, corkboard) layered on top (z-10).
export default function ScrapbookPage({ children }: { children: ReactNode }) {
  return (
    <div
      className="relative min-h-[calc(100vh-64px)] overflow-hidden"
      style={{
        backgroundColor: "var(--color-surface-2)",
        backgroundImage:
          "radial-gradient(color-mix(in srgb, var(--color-ink) 8%, transparent) 1.2px, transparent 1.2px)," +
          "radial-gradient(color-mix(in srgb, var(--color-ink) 4%, transparent) 1px, transparent 1px)",
        backgroundSize: "23px 23px, 11px 11px",
        backgroundPosition: "0 0, 6px 6px",
      }}
    >
      <PageEphemera />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
