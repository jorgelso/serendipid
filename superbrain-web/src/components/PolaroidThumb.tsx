"use client";

import { seededRotation } from "@/lib/collage";

interface PolaroidThumbProps {
  src: string;
  alt: string;
  seed: number;
  caption?: string;
  size?: "sm" | "md" | "lg";
  /** Overrides the seeded default tilt — used to spread a fanned pile of
   *  siblings across a wider angle than one shared seed would give them. */
  rotation?: number;
  className?: string;
}

const DIMS: Record<NonNullable<PolaroidThumbProps["size"]>, string> = {
  sm: "w-20 h-28",
  md: "w-28 h-36",
  lg: "w-36 h-48",
};

// A study guide's thumbnail (first PDF page) framed like a physical
// polaroid — thick white paper border, extra weight at the bottom for a
// caption, deliberately NOT theme-aware (real photo paper is white
// regardless of dark mode). Seeded tilt by default (stable across
// re-renders — the corkboard polls every few seconds while a collection is
// generating, so jittering rotation would read as broken), straightens and
// lifts to the top of the pile on hover.
export default function PolaroidThumb({ src, alt, seed, caption, size = "md", rotation, className = "" }: PolaroidThumbProps) {
  const tilt = rotation ?? seededRotation(seed, 6);
  const dims = DIMS[size];
  return (
    <div
      style={{ transform: `rotate(${tilt}deg)` }}
      className={`inline-block bg-white p-2 pb-4 shadow-[0_10px_18px_-10px_rgba(0,0,0,0.55)] transition-transform duration-300 ease-out hover:z-30 hover:rotate-0 hover:scale-105 ${className}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} className={`${dims} object-cover bg-surface-2`} loading="lazy" />
      {caption && (
        <p className={`font-hand mt-1.5 truncate text-center text-[13px] leading-none text-black/70 ${dims.split(" ")[0]}`}>
          {caption}
        </p>
      )}
    </div>
  );
}
