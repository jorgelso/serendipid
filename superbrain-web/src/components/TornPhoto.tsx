import { seededTornClip } from "@/lib/collage";

export type PhotoFrame = "torn" | "circle" | "print" | "film";

interface TornPhotoProps {
  src: string;
  alt: string;
  seed: number;
  frame: PhotoFrame;
  width: number;
  height: number;
  rotation: number;
  z: number;
  left: number;
  top: number;
  className?: string;
}

// One real source-photo fragment in the collage, always duotone-graded
// (via the page-level #collage-duotone filter, ScrapbookPage.tsx) so a pile
// of unrelated phone-video thumbnails reads as one physically printed set
// of clippings rather than mismatched screenshots — then framed as one of
// four physical materials: a torn/scissor-cut scrap, a circular photo
// punch, a white-bordered print, or a black filmstrip crop.
export default function TornPhoto({ src, alt, seed, frame, width, height, rotation, z, left, top, className = "" }: TornPhotoProps) {
  const base = {
    position: "absolute" as const,
    left,
    top,
    width,
    height,
    transform: `rotate(${rotation}deg)`,
    zIndex: z,
  };
  const imgFilter = "url(#collage-duotone) contrast(1.12)";

  if (frame === "circle") {
    return (
      <div
        style={{ ...base, borderRadius: "9999px", overflow: "hidden", boxShadow: "0 10px 20px -8px rgba(0,0,0,.6)" }}
        className={className}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} loading="lazy" className="h-full w-full object-cover" style={{ filter: imgFilter }} />
      </div>
    );
  }
  if (frame === "print") {
    return (
      // Fixed off-white, not the theme-aware --paper-bg — real photo paper
      // border stays white/cream regardless of dark mode (same convention
      // the old PolaroidThumb used).
      <div
        style={{ ...base, background: "#f6f0e2", padding: "7px 7px 22px", boxShadow: "0 14px 26px -10px rgba(0,0,0,.6)" }}
        className={className}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          loading="lazy"
          className="block h-full w-full object-cover"
          style={{ filter: imgFilter }}
        />
      </div>
    );
  }
  if (frame === "film") {
    return (
      <div style={{ ...base, background: "#0d0a07", padding: "8px 4px", boxShadow: "0 14px 26px -10px rgba(0,0,0,.6)" }} className={className}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} loading="lazy" className="h-full w-full object-cover" style={{ filter: imgFilter }} />
      </div>
    );
  }
  return (
    <div style={{ ...base, clipPath: seededTornClip(seed), boxShadow: "0 14px 26px -10px rgba(0,0,0,.6)" }} className={className}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} loading="lazy" className="h-full w-full object-cover" style={{ filter: imgFilter }} />
    </div>
  );
}
