"use client";

import { useMemo, useRef, type MouseEvent, type ReactNode } from "react";
import { seededRotation, seededTornClip } from "@/lib/collage";

interface PaperCutoutProps {
  seed: number;
  children: ReactNode;
  className?: string;
  rotationRange?: number;
}

// A "physical" scrap of paper, not a flat UI card: a torn/die-cut
// silhouette (seededTornClip, not a rectangle), a deterministic base tilt
// (stable across re-renders — this page polls every few seconds while a
// collection is generating, so a jittering rotation would read as broken),
// and two layered hover behaviors meant to read as "picking this up off
// the desk":
//   1. A live tilt that follows the cursor (perspective rotateX/rotateY,
//      mutated straight onto the DOM node via a ref rather than React
//      state, so tracking mousemove doesn't trigger a re-render per pixel).
//   2. A one-shot "wrinkle" ripple — an SVG displacement filter (feTurbulence
//      + feDisplacementMap) whose scale is animated from 0 back to 0 via an
//      SMIL <animate>, fired once per hover with .beginElement() rather
//      than left running continuously (a constantly-displacing filter reads
//      as broken/glitchy, not tactile).
export default function PaperCutout({ seed, children, className = "", rotationRange = 3 }: PaperCutoutProps) {
  const baseRotation = seededRotation(seed, rotationRange);
  const clipPath = seededTornClip(seed);
  const filterId = useMemo(() => `paper-wrinkle-${seed}`, [seed]);

  const nodeRef = useRef<HTMLDivElement>(null);
  const animateRef = useRef<SVGAnimateElement>(null);

  function handleMouseMove(e: MouseEvent<HTMLDivElement>) {
    const el = nodeRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    el.style.setProperty("--tilt-x", `${(-py * 9).toFixed(2)}deg`);
    el.style.setProperty("--tilt-y", `${(px * 9).toFixed(2)}deg`);
  }

  function handleMouseEnter() {
    nodeRef.current?.style.setProperty("--lift", "1");
    // SMILAnimateElement.beginElement() — not in the TS DOM lib's typing
    // for SVGAnimateElement in this project's target lib, hence the cast.
    (animateRef.current as unknown as { beginElement?: () => void } | null)?.beginElement?.();
  }

  function handleMouseLeave() {
    const el = nodeRef.current;
    if (!el) return;
    el.style.setProperty("--tilt-x", "0deg");
    el.style.setProperty("--tilt-y", "0deg");
    el.style.setProperty("--lift", "0");
  }

  return (
    <div className="relative">
      {/* Per-instance filter (seeded noise, so neighboring cutouts don't
          wrinkle in visible lockstep) — zero-size and aria-hidden, purely a
          filter definition, not rendered content. */}
      <svg width="0" height="0" className="absolute" aria-hidden focusable="false">
        <defs>
          <filter id={filterId} x="-15%" y="-15%" width="130%" height="130%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.025 0.045" numOctaves="2" seed={Math.abs(Math.floor(seed)) + 1} result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" xChannelSelector="R" yChannelSelector="G" scale="0">
              <animate ref={animateRef} attributeName="scale" values="0;7;0" dur="0.55s" begin="indefinite" fill="freeze" calcMode="spline" keySplines="0.3 0 0.2 1; 0.3 0 0.2 1" />
            </feDisplacementMap>
          </filter>
        </defs>
      </svg>
      <div
        ref={nodeRef}
        onMouseMove={handleMouseMove}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
                style={{
          ["--base-rotate" as string]: `${baseRotation}deg`,
          backgroundColor: "var(--paper-bg)",
          transform:
            "rotate(var(--base-rotate)) perspective(900px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg)) scale(calc(1 + var(--lift, 0) * 0.035)) translateY(calc(var(--lift, 0) * -4px))",
          clipPath,
          filter: `url(#${filterId}) drop-shadow(0 calc(6px + var(--lift, 0) * 10px) calc(10px + var(--lift, 0) * 14px) rgba(0,0,0,0.4))`,
        }}
        className={`transition-transform duration-200 ease-out will-change-transform ${className}`}
      >
        {children}
      </div>
    </div>
  );
}
