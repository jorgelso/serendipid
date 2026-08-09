"use client";

import { useRouter } from "next/navigation";

interface BrowseFiltersProps {
  categories: string[];
  languages: string[];
  collections: { id: string; name: string }[];
  category: string;
  language: string;
  collection: string;
}

export default function BrowseFilters({
  categories,
  languages,
  collections,
  category,
  language,
  collection,
}: BrowseFiltersProps) {
  const router = useRouter();

  function update(next: { category?: string; language?: string; collection?: string }) {
    const params = new URLSearchParams();
    const nextCategory = next.category ?? category;
    const nextLanguage = next.language ?? language;
    const nextCollection = next.collection ?? collection;
    if (nextCategory) params.set("category", nextCategory);
    if (nextLanguage) params.set("language", nextLanguage);
    if (nextCollection) params.set("collection", nextCollection);
    router.push(`/browse${params.toString() ? `?${params.toString()}` : ""}`);
  }

  const selectClass =
    "rounded-full border border-line bg-surface px-4 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral cursor-pointer";

  return (
    <div className="flex flex-wrap gap-3">
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

      {(category || language || collection) && (
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
