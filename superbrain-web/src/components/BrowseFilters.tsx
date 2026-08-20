"use client";

import { useRouter } from "next/navigation";

interface BrowseFiltersProps {
  categories: string[];
  languages: string[];
  collections: { id: string; name: string }[];
  category: string[];
  // "exact" (default): a post must carry ONLY categories within the
  // selection to show — keeps a "Books" browse free of posts that are also
  // tagged Humor & Memes, Events, etc. "any": broadened union match, only
  // reachable via the fallback hint's "show broader results" link.
  categoryMode: "exact" | "any";
  language: string;
  collection: string;
  sort: string;
  importance: number[];
}

const IMPORTANCE_LEVELS = [1, 2, 3, 4, 5];

export default function BrowseFilters({
  categories,
  languages,
  collections,
  category,
  categoryMode,
  language,
  collection,
  sort,
  importance,
}: BrowseFiltersProps) {
  const router = useRouter();

  function update(next: {
    category?: string[];
    language?: string;
    collection?: string;
    sort?: string;
    importance?: number[];
  }) {
    const params = new URLSearchParams();
    const nextCategory = next.category ?? category;
    const nextLanguage = next.language ?? language;
    const nextCollection = next.collection ?? collection;
    const nextSort = next.sort ?? sort;
    const nextImportance = next.importance ?? importance;
    // Picking categories fresh from this control always resets back to
    // exact match — "any" is only ever reached via the fallback hint link.
    const nextCategoryMode = next.category ? "exact" : categoryMode;
    if (nextCategory.length > 0) params.set("category", nextCategory.join(","));
    if (nextCategoryMode === "any" && nextCategory.length > 0) params.set("categoryMode", "any");
    if (nextLanguage) params.set("language", nextLanguage);
    if (nextCollection) params.set("collection", nextCollection);
    if (nextSort && nextSort !== "recent") params.set("sort", nextSort);
    if (nextImportance.length > 0) params.set("importance", nextImportance.join(","));
    router.push(`/browse${params.toString() ? `?${params.toString()}` : ""}`);
  }

  function toggleImportance(level: number) {
    const next = importance.includes(level)
      ? importance.filter((v) => v !== level)
      : [...importance, level].sort((a, b) => a - b);
    update({ importance: next });
  }

  const selectClass =
    "rounded-full border border-line bg-surface px-4 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral cursor-pointer";

  return (
    <div className="flex flex-wrap items-start gap-3">
      <div className="flex flex-col gap-1">
        <select
          multiple
          size={Math.min(6, Math.max(2, categories.length))}
          value={category}
          onChange={(e) =>
            update({ category: Array.from(e.target.selectedOptions, (o) => o.value) })
          }
          className="w-44 rounded-2xl border border-line bg-surface px-3 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral cursor-pointer"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <span className="pl-1 text-[11px] text-ink-muted">
          ⌘/Ctrl-click for multiple · none selected = all
        </span>
      </div>

      <select
        value={language}
        onChange={(e) => update({ language: e.target.value })}
        className={selectClass}
      >
        <option value="">All languages</option>
        {languages.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>

      <select
        value={collection}
        onChange={(e) => update({ collection: e.target.value })}
        className={selectClass}
      >
        <option value="">All collections</option>
        {collections.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      <select
        value={sort}
        onChange={(e) => update({ sort: e.target.value })}
        className={selectClass}
      >
        <option value="recent">Sort: Recent</option>
        <option value="importance">Sort: Most important</option>
      </select>

      <div className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-1.5">
        <span className="pl-1.5 pr-0.5 text-xs font-bold text-ink-muted">Importance</span>
        {IMPORTANCE_LEVELS.map((level) => {
          const active = importance.includes(level);
          return (
            <button
              key={level}
              type="button"
              onClick={() => toggleImportance(level)}
              aria-pressed={active}
              className={`h-7 w-7 rounded-full text-sm font-bold transition-colors cursor-pointer ${
                active
                  ? "bg-coral text-white"
                  : "text-ink-muted hover:bg-line/40"
              }`}
            >
              {level}
            </button>
          );
        })}
      </div>

      {(category.length > 0 ||
        language ||
        collection ||
        (sort && sort !== "recent") ||
        importance.length > 0) && (
        <button
          onClick={() => router.push("/browse")}
          className="rounded-full px-4 py-2 text-sm font-bold text-ink-muted hover:text-coral-ink transition-colors"
        >
          Clear
        </button>
      )}
    </div>
  );
}
