"use client";

import { useMemo, useState } from "react";
import type { Theme, VectorSpaceColorSlot } from "@/types/domain";
import { colorForSlot, useVizPalette } from "@/lib/useVizPalette";

// Sentinel for the "no theme" bucket, safe to compare against real theme ids
// since computeThemes() (src/lib/clustering.ts) always ids themes "theme-N".
export const UNCLUSTERED_SELECTION = "__unclustered__";

interface LegendEntry {
  key: string; // theme.id, or UNCLUSTERED_SELECTION
  colorSlot: VectorSpaceColorSlot;
  label: string;
  count: number;
}

interface VectorSpaceLegendProps {
  themes: Theme[];
  unclusteredCount: number;
  activeSelection: string | null;
  onSelect: (key: string | null) => void;
}

// The first 8 themes (already largest-first from computeThemes()) get their
// own validated categorical hue; anything past that shares the neutral
// "other" swatch, per the dataviz skill's scatter series cap — but every
// theme still gets its own row here and is individually selectable by
// theme id, not just lumped into an unclickable "Other themes" count. Color
// is capped at 8 distinguishable hues; visibility/selectability isn't.
function buildEntries(themes: Theme[], unclusteredCount: number): LegendEntry[] {
  const entries: LegendEntry[] = themes.map((theme, i) => ({
    key: theme.id,
    colorSlot: i < 8 ? `theme-${i}` : "other",
    label: theme.label,
    count: theme.postCount,
  }));

  if (unclusteredCount > 0) {
    entries.push({
      key: UNCLUSTERED_SELECTION,
      colorSlot: "unclustered",
      label: "Unclustered",
      count: unclusteredCount,
    });
  }

  return entries;
}

function LegendRow({
  entry,
  isActive,
  isDimmed,
  onClick,
}: {
  entry: LegendEntry;
  isActive: boolean;
  isDimmed: boolean;
  onClick: () => void;
}) {
  const palette = useVizPalette();
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs font-semibold transition-colors ${
        isActive ? "bg-surface-2" : "hover:bg-surface-2"
      } ${isDimmed ? "opacity-40" : ""}`}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: colorForSlot(palette, entry.colorSlot) }}
      />
      <span className="flex-1 truncate">{entry.label}</span>
      <span className="text-ink-muted">{entry.count}</span>
    </button>
  );
}

const VISIBLE_CAP = 8;

export default function VectorSpaceLegend({
  themes,
  unclusteredCount,
  activeSelection,
  onSelect,
}: VectorSpaceLegendProps) {
  const [expanded, setExpanded] = useState(false);
  const entries = useMemo(() => buildEntries(themes, unclusteredCount), [themes, unclusteredCount]);

  if (entries.length === 0) return null;

  const primary = entries.slice(0, VISIBLE_CAP);
  const rest = entries.slice(VISIBLE_CAP);

  return (
    <div className="pointer-events-auto flex max-h-[70vh] w-56 flex-col gap-1 overflow-y-auto rounded-2xl border border-line bg-surface/90 p-3 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
      <div className="flex items-center justify-between px-1 pb-1">
        <span className="font-display text-xs font-bold text-ink-muted uppercase tracking-wide">
          Clusters
        </span>
        {activeSelection !== null && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="text-[11px] font-bold text-coral-ink hover:underline"
          >
            Show all
          </button>
        )}
      </div>
      {primary.map((entry) => (
        <LegendRow
          key={entry.key}
          entry={entry}
          isActive={activeSelection === entry.key}
          isDimmed={activeSelection !== null && activeSelection !== entry.key}
          onClick={() => onSelect(activeSelection === entry.key ? null : entry.key)}
        />
      ))}
      {rest.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-2 rounded-xl px-2 py-1.5 text-left text-xs font-semibold text-ink-muted hover:bg-surface-2"
          >
            <span className="w-2.5 shrink-0 text-center">{expanded ? "−" : "+"}</span>
            <span className="flex-1 truncate">
              {expanded ? "Hide" : "Show"} {rest.length} more theme{rest.length === 1 ? "" : "s"}
            </span>
            <span className="text-ink-muted">{rest.reduce((sum, e) => sum + e.count, 0)}</span>
          </button>
          {expanded &&
            rest.map((entry) => (
              <LegendRow
                key={entry.key}
                entry={entry}
                isActive={activeSelection === entry.key}
                isDimmed={activeSelection !== null && activeSelection !== entry.key}
                onClick={() => onSelect(activeSelection === entry.key ? null : entry.key)}
              />
            ))}
        </>
      )}
    </div>
  );
}
