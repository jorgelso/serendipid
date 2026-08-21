import type { TapeColor } from "@/lib/collage";

// Hue-rotate per accent color, applied to the one real photographed tape
// strip below — keeps per-instance color variety from a single physical
// asset instead of needing one photo per color.
const TAPE_HUE: Record<TapeColor, number> = {
  yellow: 0,
  coral: 320,
  teal: 150,
  lavender: 250,
  mint: 110,
  rose: 335,
  sky: 190,
};

interface WashiTapeProps {
  color?: TapeColor;
  rotation?: number;
  className?: string;
}

// A strip of real photographed washi tape (torn ends, woven texture) pinning
// a scrap down — a photo, not a CSS gradient, so it reads as physical tape
// rather than a flat digital stripe.
export default function WashiTape({ color = "yellow", rotation = -6, className = "" }: WashiTapeProps) {
  return (
    <span
      aria-hidden
      style={{ transform: `translateX(-50%) rotate(${rotation}deg)` }}
      className={`pointer-events-none absolute left-1/2 -top-3 z-10 w-14 ${className}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/collage/tape.png"
        alt=""
        className="block w-full drop-shadow-[0_3px_5px_rgba(0,0,0,0.4)]"
        style={{ filter: `hue-rotate(${TAPE_HUE[color]}deg) saturate(1.1)` }}
      />
    </span>
  );
}
