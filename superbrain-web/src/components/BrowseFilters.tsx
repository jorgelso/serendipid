"use client";

import { useRouter } from "next/navigation";

interface BrowseFiltersProps {
  categories: string[];
  languages: string[];
  collections: { id: string; name: string }[];
  category: string;
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
  language,
  collection,
  sort,
  importance,
}: BrowseFiltersProps) {
  const router = useRouter();

  function update(next: {
    category?: string;
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
    if (nextCategory) params.set("category", nextCategory);
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
    <div className="flex flex-wrap items-center gap-3">
      <select
        value={category}
        onChange={(e) => update({ category: e.target.value })}
        className={selectClass}
      >
        <option value="">All categories</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

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

      {(category || language || collection || (sort && sort !== "recent") || importance.length > 0) && (
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
