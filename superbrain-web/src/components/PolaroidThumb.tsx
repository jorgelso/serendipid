"use client";

import { seededRotation } from "@/lib/collage";

interface PolaroidThumbProps {
  src: string;
  alt: string;
  seed: number;
  caption?: string;
  size?: "sm" | "md";
}

// A study guide's thumbnail (first PDF page) framed like a physical
// polaroid — thick white paper border, extra weight at the bottom for a
// caption, deliberately NOT theme-aware (real photo paper is white
// regardless of dark mode), with the same seeded-tilt/straighten-on-hover
// treatment as PaperCutout.
export default function PolaroidThumb({ src, alt, seed, caption, size = "md" }: PolaroidThumbProps) {
  const rotation = seededRotation(seed, 6);
  const dims = size === "sm" ? "w-20 h-28" : "w-28 h-36";
  return (
    <div
      style={{ transform: `rotate(${rotation}deg)` }}
      className="inline-block bg-white p-2 pb-4 shadow-[0_10px_18px_-10px_rgba(0,0,0,0.55)] transition-transform duration-300 ease-out hover:rotate-0 hover:scale-105"
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
