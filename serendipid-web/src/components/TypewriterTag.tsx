import type { ReactNode } from "react";

interface TypewriterTagProps {
  children: ReactNode;
  rotation?: number;
  className?: string;
}

// A strip of "typewritten" metadata — a distinct scrap of source material
// (monospace, cream stock, hard-edged) from the handwritten title chips and
// hand-drawn stickers around it, so a collage cluster reads as several
// different found materials pinned together rather than one repeated card
// pattern wearing different text.
export default function TypewriterTag({ children, rotation = 0, className = "" }: TypewriterTagProps) {
  return (
    <span
      style={{ transform: `rotate(${rotation}deg)`, backgroundColor: "var(--paper-bg)", color: "var(--color-ink)" }}
      className={`inline-block border border-black/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide whitespace-nowrap uppercase shadow-[0_3px_6px_rgba(0,0,0,0.35)] ${className}`}
    >
      {children}
    </span>
  );
}
