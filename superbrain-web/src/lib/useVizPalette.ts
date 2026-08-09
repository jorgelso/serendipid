"use client";

// Reads the /space view's categorical palette (globals.css --viz-series-1..8
// + --viz-neutral) as resolved hex strings. three.js material colors need an
// actual value, not a CSS custom property, so this is the one place that
// bridges the app's existing CSS-variable theming (media query +
// data-theme escape hatch, see globals.css) into JS — re-reading whenever
// either theme signal changes rather than hardcoding a light/dark hex table
// a second time.

import { useEffect, useState } from "react";
import type { VectorSpaceColorSlot } from "@/types/domain";

export type VizPalette = Record<string, string>;

const SERIES_COUNT = 8;

function readPalette(): VizPalette {
  const style = getComputedStyle(document.documentElement);
  const palette: VizPalette = { neutral: style.getPropertyValue("--viz-neutral").trim() };
  for (let i = 0; i < SERIES_COUNT; i++) {
    palette[`theme-${i}`] = style.getPropertyValue(`--viz-series-${i + 1}`).trim();
  }
  return palette;
}

export function useVizPalette(): VizPalette {
  // Starts empty on both server and client (colorForSlot's fallback covers
  // it) rather than branching on typeof window during the initial render —
  // that branch is exactly what causes a hydration mismatch (this component
  // does SSR, e.g. VectorSpaceLegend; readPalette() needs a real `window`,
  // so it can only ever run after mount). The real palette lands one paint
  // later, via the effect below.
  const [palette, setPalette] = useState<VizPalette>({});

  useEffect(() => {
    const refresh = () => setPalette(readPalette());
    refresh();

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", refresh);

    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      media.removeEventListener("change", refresh);
      observer.disconnect();
    };
  }, []);

  return palette;
}

export function colorForSlot(palette: VizPalette, slot: VectorSpaceColorSlot): string {
  if (slot === "other" || slot === "unclustered") return palette.neutral ?? "#898781";
  return palette[slot] ?? palette.neutral ?? "#898781";
}
