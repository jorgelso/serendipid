"use client";

// Reads the /space view's categorical palette (globals.css --viz-series-1..24
// + --viz-neutral) as resolved hex strings. three.js material colors need an
// actual value, not a CSS custom property, so this is the one place that
// bridges the app's existing CSS-variable theming (media query +
// data-theme escape hatch, see globals.css) into JS — re-reading whenever
// either theme signal changes rather than hardcoding a light/dark hex table
// a second time.

import { useEffect, useState } from "react";
import * as THREE from "three";
import type { VectorSpaceColorSlot } from "@/types/domain";

export type VizPalette = Record<string, string>;

const SERIES_COUNT = 24;

// How many largest themes are colored/shown by default before the legend
// requires expanding (VectorSpaceLegend.tsx). Also read by VectorSpaceScene
// to gray out points past this rank when the legend is collapsed — shared
// here so the two stay in sync rather than each hardcoding "8".
export const LEGEND_VISIBLE_CAP = 8;

// Extracts a colorSlot's theme rank ("theme-11" -> 11); null for "other" /
// "unclustered", which have no rank.
export function seriesIndex(slot: VectorSpaceColorSlot): number | null {
  if (!slot.startsWith("theme-")) return null;
  const n = Number(slot.slice("theme-".length));
  return Number.isFinite(n) ? n : null;
}

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

const HUE_ANCHOR_COUNT = 8;
const DUAL_SLOT_COUNT = 16; // repeat slots 8-23
const MAX_PAIR_USES_PER_HUE = (DUAL_SLOT_COUNT * 2) / HUE_ANCHOR_COUNT; // 4 — keeps every hue used about evenly

function circularHueDistance(a: number, b: number): number {
  const diff = Math.abs(a - b) % 360;
  return diff > 180 ? 360 - diff : diff;
}

// Slots 0-7 (theme-0..theme-7) are the palette's 8 base anchor hues; slots
// 8-23 are lighter/darker repeats of those same 8 (see globals.css's
// --viz-series comment) — visually "another slightly different red" once a
// library has enough themes to reach them. Rather than let a repeat slot
// stay a near-duplicate of an already-used hue, each one is redefined as a
// PAIR of two distinct base hues, rendered as a two-tone split sphere
// (VectorSpaceScene's DualCoreLayer) instead of a single repeated color.
//
// Pairs are chosen by the anchors' ACTUAL hue angle, not by how far apart
// two slot indices are — an earlier version used index distance and still
// produced a near-identical-looking pair (two of the 8 anchors are both
// greens, ~35° apart in hue, despite being 3 apart in index) since the 8
// anchors aren't evenly spaced around the hue wheel to begin with. This
// greedily takes the highest-circular-distance pair first, capping how many
// times any one hue can be reused (MAX_PAIR_USES_PER_HUE) so the 16 slots
// don't all lean on the same 2-3 "easy" opposite pairs.
function computeDualHuePairs(palette: VizPalette): [number, number][] {
  const hueAngles = Array.from({ length: HUE_ANCHOR_COUNT }, (_, i) => {
    const color = new THREE.Color(colorForSlot(palette, `theme-${i}`));
    const hsl = { h: 0, s: 0, l: 0 };
    color.getHSL(hsl);
    return hsl.h * 360;
  });

  const candidates: { pair: [number, number]; distance: number }[] = [];
  for (let i = 0; i < HUE_ANCHOR_COUNT; i++) {
    for (let j = i + 1; j < HUE_ANCHOR_COUNT; j++) {
      candidates.push({ pair: [i, j], distance: circularHueDistance(hueAngles[i], hueAngles[j]) });
    }
  }
  candidates.sort((a, b) => b.distance - a.distance);

  const usage = new Array(HUE_ANCHOR_COUNT).fill(0);
  const chosen: [number, number][] = [];
  for (const { pair } of candidates) {
    if (chosen.length >= DUAL_SLOT_COUNT) break;
    const [a, b] = pair;
    if (usage[a] >= MAX_PAIR_USES_PER_HUE || usage[b] >= MAX_PAIR_USES_PER_HUE) continue;
    usage[a]++;
    usage[b]++;
    chosen.push(pair);
  }
  // The cap above can (rarely, depending on the anchors' actual hue
  // distribution) leave a couple of slots short of DUAL_SLOT_COUNT — a
  // second, uncapped pass by distance guarantees every repeat slot still
  // gets a pair rather than falling back to a single repeated hue.
  if (chosen.length < DUAL_SLOT_COUNT) {
    const chosenKeys = new Set(chosen.map(([a, b]) => `${a}-${b}`));
    for (const { pair } of candidates) {
      if (chosen.length >= DUAL_SLOT_COUNT) break;
      if (chosenKeys.has(`${pair[0]}-${pair[1]}`)) continue;
      chosen.push(pair);
    }
  }
  return chosen;
}

// Callers memoize computeDualHuePairs() themselves (it's not a hook, so it
// can be called from inside a .map() the way VectorSpaceScene/
// VectorSpaceLegend do) and pass the result in here. Returns null for the
// 8 pure slots (and "other"/"unclustered") — those stay single-color.
export function dualHueSlotsForSlot(
  slot: VectorSpaceColorSlot,
  dualHuePairs: [number, number][]
): [VectorSpaceColorSlot, VectorSpaceColorSlot] | null {
  const idx = seriesIndex(slot);
  if (idx === null || idx < HUE_ANCHOR_COUNT) return null;
  const pair = dualHuePairs[idx - HUE_ANCHOR_COUNT];
  if (!pair) return null;
  const [a, b] = pair;
  return [`theme-${a}`, `theme-${b}`];
}

export { computeDualHuePairs };

// The app's --viz-series anchors are a deliberately restrained "Bright
// Pulse" pastel palette — fine as a single flat dot, but per direct
// testing, not enough contrast for a two-tone split sphere's two halves to
// read as clearly different colors, especially small/glowing/at a
// distance. This boosts saturation and pins lightness to 0.5 — in HSL,
// that's the point of maximum vividness for a given hue; moving away from
// it in either direction (as an earlier version's l=0.58 did) desaturates
// the *perceived* color back toward white/black even at high s, which
// undercut the whole point of this function. Specific to dual-slot
// rendering (DualCoreLayer's colorA/colorB, and the legend's split swatch)
// — doesn't touch the palette itself, so the 8 pure slots and the rest of
// the app are unaffected.
export function vividColorForSlot(palette: VizPalette, slot: VectorSpaceColorSlot): string {
  const color = new THREE.Color(colorForSlot(palette, slot));
  const hsl = { h: 0, s: 0, l: 0 };
  color.getHSL(hsl);
  color.setHSL(hsl.h, 1, 0.5);
  return `#${color.getHexString()}`;
}
