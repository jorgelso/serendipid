"use client";

import { useEffect, useRef, useState } from "react";
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
  dir: "asc" | "desc";
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
  dir,
  importance,
}: BrowseFiltersProps) {
  const router = useRouter();
  const [categoryOpen, setCategoryOpen] = useState(false);
  const categoryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!categoryOpen) return;
    function onPointerDown(e: MouseEvent) {
      if (categoryRef.current && !categoryRef.current.contains(e.target as Node)) {
        setCategoryOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setCategoryOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [categoryOpen]);

  function update(next: {
    category?: string[];
    language?: string;
    collection?: string;
    sort?: string;
    dir?: "asc" | "desc";
    importance?: number[];
  }) {
    const params = new URLSearchParams();
    const nextCategory = next.category ?? category;
    const nextLanguage = next.language ?? language;
    const nextCollection = next.collection ?? collection;
    const nextSort = next.sort ?? sort;
    const nextDir = next.dir ?? dir;
    const nextImportance = next.importance ?? importance;
    // Picking categories fresh from this control always resets back to
    // exact match — "any" is only ever reached via the fallback hint link.
    const nextCategoryMode = next.category ? "exact" : categoryMode;
    if (nextCategory.length > 0) params.set("category", nextCategory.join(","));
    if (nextCategoryMode === "any" && nextCategory.length > 0) params.set("categoryMode", "any");
    if (nextLanguage) params.set("language", nextLanguage);
    if (nextCollection) params.set("collection", nextCollection);
    if (nextSort && nextSort !== "date_saved") params.set("sort", nextSort);
    if (nextDir && nextDir !== "desc") params.set("dir", nextDir);
    if (nextImportance.length > 0) params.set("importance", nextImportance.join(","));
    router.push(`/browse${params.toString() ? `?${params.toString()}` : ""}`);
  }

  function toggleImportance(level: number) {
    const next = importance.includes(level)
      ? importance.filter((v) => v !== level)
      : [...importance, level].sort((a, b) => a - b);
    update({ importance: next });
  }

  function toggleCategory(c: string) {
    const next = category.includes(c) ? category.filter((v) => v !== c) : [...category, c];
    update({ category: next });
  }

  const selectClass =
    "rounded-full border border-line bg-surface px-4 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral cursor-pointer";

  const categoryLabel =
    category.length === 0
      ? "All categories"
      : category.length === 1
        ? category[0]
        : `${category.length} categories`;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative" ref={categoryRef}>
        <button
          type="button"
          onClick={() => setCategoryOpen((v) => !v)}
          aria-expanded={categoryOpen}
          className={`${selectClass} flex items-center gap-1.5`}
        >
          <span className="max-w-40 truncate">{categoryLabel}</span>
          <span className="text-xs text-ink-muted">▾</span>
        </button>
        {categoryOpen && (
          <div className="absolute z-10 mt-2 max-h-72 w-64 overflow-y-auto rounded-2xl border border-line bg-surface p-2 shadow-lg">
            <p className="px-2 pb-1 text-[11px] text-ink-muted">
              Check to include · none checked = all
            </p>
            {categories.map((c) => (
              <label
                key={c}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ink hover:bg-line/40"
              >
                <input
                  type="checkbox"
                  checked={category.includes(c)}
                  onChange={() => toggleCategory(c)}
                  className="h-4 w-4 cursor-pointer accent-coral"
                />
                {c}
              </label>
            ))}
          </div>
        )}
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
        <option value="date_saved">Sort: Save date</option>
        <option value="post_date">Sort: Publish date</option>
      </select>

      <button
        type="button"
        onClick={() => update({ dir: dir === "asc" ? "desc" : "asc" })}
        aria-label={dir === "asc" ? "Sort ascending" : "Sort descending"}
        title={dir === "asc" ? "Ascending (oldest/lowest first)" : "Descending (newest/highest first)"}
        className={`${selectClass} flex items-center gap-1`}
      >
        <span aria-hidden>{dir === "asc" ? "↑" : "↓"}</span>
        {dir === "asc" ? "Ascending" : "Descending"}
      </button>

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
        (sort && sort !== "date_saved") ||
        dir !== "desc" ||
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
