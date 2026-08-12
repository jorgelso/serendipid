"use client";

import { useRouter } from "next/navigation";

interface EloquenceFiltersProps {
  tutorial: "" | "yes" | "no";
}

const TABS: { value: "" | "yes" | "no"; label: string }[] = [
  { value: "", label: "All" },
  { value: "no", label: "Non-tutorials" },
  { value: "yes", label: "Tutorials" },
];

export default function EloquenceFilters({ tutorial }: EloquenceFiltersProps) {
  const router = useRouter();

  function update(next: "" | "yes" | "no") {
    router.push(`/eloquent${next ? `?tutorial=${next}` : ""}`);
  }

  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-line bg-surface p-1">
      {TABS.map((tab) => {
        const active = tab.value === tutorial;
        return (
          <button
            key={tab.value || "all"}
            type="button"
            onClick={() => update(tab.value)}
            aria-pressed={active}
            className={`rounded-full px-4 py-1.5 text-sm font-bold transition-colors cursor-pointer ${
              active ? "bg-ink text-bg" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
