"use client";

import { useMemo } from "react";
import type { Theme, VectorSpaceColorSlot } from "@/types/domain";
import { colorForSlot, useVizPalette } from "@/lib/useVizPalette";

interface LegendEntry {
  slot: VectorSpaceColorSlot;
  label: string;
  count: number;
}

interface VectorSpaceLegendProps {
  themes: Theme[];
  unclusteredCount: number;
  activeColorSlot: VectorSpaceColorSlot | null;
  onSelectSlot: (slot: VectorSpaceColorSlot | null) => void;
}

// Mirrors buildThemeAssignments() in src/lib/vectorSpace.ts: the first 8
// themes (already largest-first from computeThemes()) get their own
// validated categorical hue; anything past that folds into "Other" rather
// than reusing a color, per the dataviz skill's scatter series cap.
function buildLegendEntries(themes: Theme[], unclusteredCount: number): LegendEntry[] {
  const entries: LegendEntry[] = themes.slice(0, 8).map((theme, i) => ({
    slot: `theme-${i}`,
    label: theme.label,
    count: theme.postCount,
  }));

  const otherCount = themes.slice(8).reduce((sum, t) => sum + t.postCount, 0);
  if (otherCount > 0) {
    entries.push({ slot: "other", label: "Other themes", count: otherCount });
  }
  if (unclusteredCount > 0) {
    entries.push({ slot: "unclustered", label: "Unclustered", count: unclusteredCount });
  }

  return entries;
}

export default function VectorSpaceLegend({
  themes,
  unclusteredCount,
  activeColorSlot,
  onSelectSlot,
}: VectorSpaceLegendProps) {
  const palette = useVizPalette();
  const entries = useMemo(() => buildLegendEntries(themes, unclusteredCount), [themes, unclusteredCount]);

  if (entries.length === 0) return null;

  return (
    <div className="pointer-events-auto flex max-h-[70vh] w-56 flex-col gap-1 overflow-y-auto rounded-2xl border border-line bg-surface/90 p-3 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
      <div className="flex items-center justify-between px-1 pb-1">
        <span className="font-display text-xs font-bold text-ink-muted uppercase tracking-wide">
          Clusters
        </span>
        {activeColorSlot !== null && (
          <button
            type="button"
            onClick={() => onSelectSlot(null)}
            className="text-[11px] font-bold text-coral-ink hover:underline"
          >
            Show all
          </button>
        )}
      </div>
      {entries.map((entry) => {
        const isActive = activeColorSlot === entry.slot;
        const isDimmed = activeColorSlot !== null && !isActive;
        return (
          <button
            key={entry.slot}
            type="button"
            onClick={() => onSelectSlot(isActive ? null : entry.slot)}
            className={`flex items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs font-semibold transition-colors ${
              isActive ? "bg-surface-2" : "hover:bg-surface-2"
            } ${isDimmed ? "opacity-40" : ""}`}
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: colorForSlot(palette, entry.slot) }}
            />
            <span className="flex-1 truncate">{entry.label}</span>
            <span className="text-ink-muted">{entry.count}</span>
          </button>
        );
      })}
    </div>
  );
}
