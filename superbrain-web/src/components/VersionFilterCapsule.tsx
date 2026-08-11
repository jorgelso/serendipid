"use client";

import type { VersionFilters } from "@/lib/posts";
import { colorFor } from "./Chips";

interface VersionFilterCapsuleProps {
  categories: string[];
  languages: string[];
  value: VersionFilters;
  onChange: (next: VersionFilters) => void;
}

const NEUTRAL_PILL = "shrink-0 rounded-full text-[11px] font-bold px-3 py-1.5 whitespace-nowrap transition-colors";

// Horizontal capsule row of toggle pills (category / language / sort) — not
// <select> dropdowns like BrowseFilters, per the /versions page's design:
// pinned above the horizontally-paged version panels, applying to whichever
// panel is active.
export default function VersionFilterCapsule({ categories, languages, value, onChange }: VersionFilterCapsuleProps) {
  const hasFilter = value.category || value.language || value.sort !== "recent";

  return (
    <div className="flex items-center gap-2 overflow-x-auto px-5 py-2.5">
      <button
        onClick={() => onChange({ category: "", language: "", sort: "recent" })}
        className={`${NEUTRAL_PILL} ${!hasFilter ? "bg-ink text-bg" : "bg-surface-2 text-ink-muted hover:text-ink"}`}
      >
        All
      </button>

      <button
        onClick={() => onChange({ ...value, sort: value.sort === "importance" ? "recent" : "importance" })}
        className={`${NEUTRAL_PILL} ${
          value.sort === "importance" ? "bg-yellow-ink text-bg" : "bg-surface-2 text-ink-muted hover:text-ink"
        }`}
      >
        ⭐ Most important
      </button>

      {languages.length > 0 && <span className="shrink-0 w-px h-4 bg-line mx-1" />}
      {languages.map((lang) => (
        <button
          key={lang}
          onClick={() => onChange({ ...value, language: value.language === lang ? "" : lang })}
          className={`${NEUTRAL_PILL} ${
            value.language === lang ? "bg-ink text-bg" : "bg-surface-2 text-ink-muted hover:text-ink"
          }`}
        >
          🌐 {lang}
        </button>
      ))}

      {categories.length > 0 && <span className="shrink-0 w-px h-4 bg-line mx-1" />}
      {categories.map((category) => {
        const { bg, fg } = colorFor(category);
        const selected = value.category === category;
        return (
          <button
            key={category}
            onClick={() => onChange({ ...value, category: selected ? "" : category })}
            className="shrink-0 font-display text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1.5 rounded-full whitespace-nowrap"
            style={{
              backgroundColor: bg,
              color: fg,
              boxShadow: selected ? `0 0 0 2px ${fg}` : "none",
            }}
          >
            {category}
          </button>
        );
      })}
    </div>
  );
}
