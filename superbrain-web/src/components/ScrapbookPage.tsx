import type { ReactNode } from "react";

// A shared warm duotone (maps grayscale straight to the app's --bg/--paper-bg
// tones) applied to every real source-photo fragment in the collage
// (TornPhoto.tsx, via `filter: url(#collage-duotone)`). This is what makes a
// dozen unrelated phone-video screenshots read as one physically-printed set
// of clippings instead of a pile of random app captures — without it, each
// fragment keeps its own wildly different color/exposure and the page never
// reads as one collage. One shared filter def (not per-instance) since,
// unlike PaperCutout's wrinkle filter, this needs no per-fragment noise seed.
function CollageFilters() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden focusable="false">
      <defs>
        <filter id="collage-duotone" colorInterpolationFilters="sRGB">
          <feColorMatrix type="saturate" values="0" />
          <feComponentTransfer>
            <feFuncR type="table" tableValues="0.165 0.933" />
            <feFuncG type="table" tableValues="0.110 0.867" />
            <feFuncB type="table" tableValues="0.071 0.737" />
          </feComponentTransfer>
        </filter>
      </defs>
    </svg>
  );
}

// The full-bleed "scrapbook spread" surface for the whole /study-guides
// page — NOT one bordered box holding tidy cards, the entire page below
// the header is the textured page, with content (masthead, corkboard)
// layered on top (z-10). The corkboard itself is dense enough now (see
// StudyGuideCorkboard's scatter fill) that this page background only needs
// to supply the base texture, not its own ephemera.
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
      <CollageFilters />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
