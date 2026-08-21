import type { CSSProperties } from "react";
import { seededRotation, seededTapeColor, type TapeColor } from "@/lib/collage";

interface CutoutChipProps {
  children: string;
  seed: number;
  rotationRange?: number;
  size?: "sm" | "md" | "lg";
  className?: string;
  style?: CSSProperties;
}

const SIZE_CLASS: Record<NonNullable<CutoutChipProps["size"]>, string> = {
  sm: "rounded-[3px] px-1.5 py-0.5 text-[11px]",
  md: "rounded-[4px] px-2.5 py-1 text-base",
  lg: "rounded-[4px] px-3 py-1 text-4xl sm:text-5xl",
};

// A single "magazine cutout" letterform chip — a solid-color die-cut block
// of text, not a caption. Used both for the page masthead (one word per
// chip) and per-guide titles on the corkboard, so title text always reads
// as a pinned/pasted fragment rather than UI copy.
export default function CutoutChip({ children, seed, rotationRange = 5, size = "md", className = "", style }: CutoutChipProps) {
  const color: TapeColor = seededTapeColor(seed);
  return (
    <span
      style={{
        transform: `rotate(${seededRotation(seed, rotationRange)}deg)`,
        backgroundColor: `var(--color-${color}-soft)`,
        color: `var(--color-${color}-ink)`,
        ...style,
      }}
      className={`font-display inline-block font-bold shadow-[0_4px_8px_rgba(0,0,0,0.3)] ${SIZE_CLASS[size]} ${className}`}
    >
      {children}
    </span>
  );
}
