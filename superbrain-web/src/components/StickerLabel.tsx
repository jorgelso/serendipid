import type { ReactNode } from "react";

interface StickerLabelProps {
  children: ReactNode;
  color: string;
  rotation?: number;
  className?: string;
}

// A small die-cut "sticker" label — used for status/role callouts so they
// read as taped-on ephemera rather than a plain UI badge. Extracted out of
// StudyGuideCorkboard so it can also be pinned onto fanned-out sibling
// thumbnails, not just the one collection-level status line.
export default function StickerLabel({ children, color, rotation = -2, className = "" }: StickerLabelProps) {
  return (
    <span
      style={{ transform: `rotate(${rotation}deg)`, backgroundColor: `var(--color-${color}-soft)`, color: `var(--color-${color}-ink)` }}
      className={`font-hand inline-block rounded-[3px] px-2 py-0.5 text-[13px] font-bold leading-none shadow-[0_2px_4px_rgba(0,0,0,0.25)] ${className}`}
    >
      {children}
    </span>
  );
}
