import type { TapeColor } from "@/lib/collage";

const TAPE_BG: Record<TapeColor, string> = {
  coral: "bg-coral-soft",
  teal: "bg-teal-soft",
  lavender: "bg-lavender-soft",
  yellow: "bg-yellow-soft",
  mint: "bg-mint-soft",
  rose: "bg-rose-soft",
  sky: "bg-sky-soft",
};

interface WashiTapeProps {
  color?: TapeColor;
  rotation?: number;
  className?: string;
}

// Decorative strip of "tape" pinning a scrapbook card down — purely visual
// (aria-hidden), a translucent striped rectangle in one of the app's
// existing accent tones so it stays on-palette in both themes.
export default function WashiTape({ color = "yellow", rotation = -6, className = "" }: WashiTapeProps) {
  return (
    <span
      aria-hidden
      style={{
        transform: `translateX(-50%) rotate(${rotation}deg)`,
        backgroundImage:
          "repeating-linear-gradient(45deg, rgba(0,0,0,0.05) 0 3px, transparent 3px 7px)",
      }}
      className={`pointer-events-none absolute left-1/2 -top-3 z-10 h-6 w-20 ${TAPE_BG[color]} opacity-90 border-x border-black/5 shadow-sm ${className}`}
    />
  );
}
