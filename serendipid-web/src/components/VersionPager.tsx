"use client";

import { useRef, useState } from "react";
import type { ClientPost } from "@/types/domain";
import type { VersionFilters, VersionSummary } from "@/lib/posts";
import VersionFilterCapsule from "./VersionFilterCapsule";
import VersionPanel from "./VersionPanel";

interface VersionPagerProps {
  summaries: VersionSummary[];
  initialVersion: number;
  initialPosts: ClientPost[];
  initialTotal: number;
  categories: string[];
  languages: string[];
}

// Horizontal scroll-snap paging between one full-screen panel per
// analysis_version. All panels stay mounted simultaneously (scroll-snap just
// moves which one is in view) — VersionPanel relies on that to keep its
// fetched posts and any in-flight bulk-rescan progress alive across paging.
export default function VersionPager({
  summaries,
  initialVersion,
  initialPosts,
  initialTotal,
  categories,
  languages,
}: VersionPagerProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(() =>
    Math.max(0, summaries.findIndex((s) => s.version === initialVersion))
  );
  const [filters, setFilters] = useState<VersionFilters>({ category: "", language: "", sort: "recent" });

  function scrollToIndex(i: number) {
    const el = scrollerRef.current;
    if (!el) return;
    const clamped = Math.max(0, Math.min(summaries.length - 1, i));
    el.scrollTo({ left: clamped * el.clientWidth, behavior: "smooth" });
  }

  function handleScroll() {
    const el = scrollerRef.current;
    if (!el || el.clientWidth === 0) return;
    const i = Math.round(el.scrollLeft / el.clientWidth);
    setActiveIndex((prev) => (prev === i ? prev : i));
  }

  const active = summaries[activeIndex] as VersionSummary | undefined;

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-line bg-bg">
        <VersionFilterCapsule categories={categories} languages={languages} value={filters} onChange={setFilters} />
      </div>

      <div className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm border-b border-line bg-surface">
        <button
          onClick={() => scrollToIndex(activeIndex - 1)}
          disabled={activeIndex === 0}
          className="rounded-full px-3 py-1 font-bold text-ink-muted hover:text-ink disabled:opacity-30 disabled:hover:text-ink-muted transition-colors"
        >
          ← Prev
        </button>
        <span className="font-display font-semibold">
          {active ? `Version ${active.version}` : ""}{" "}
          <span className="text-ink-muted font-body font-normal">
            · {activeIndex + 1} of {summaries.length}
          </span>
        </span>
        <button
          onClick={() => scrollToIndex(activeIndex + 1)}
          disabled={activeIndex === summaries.length - 1}
          className="rounded-full px-3 py-1 font-bold text-ink-muted hover:text-ink disabled:opacity-30 disabled:hover:text-ink-muted transition-colors"
        >
          Next →
        </button>
      </div>

      <div
        ref={scrollerRef}
        onScroll={handleScroll}
        className="flex-1 flex overflow-x-auto snap-x snap-mandatory scroll-smooth"
      >
        {summaries.map((summary, i) => (
          <div key={summary.version} className="snap-start shrink-0 w-full h-full overflow-hidden">
            <VersionPanel
              summary={summary}
              filters={filters}
              isActive={i === activeIndex}
              initialPosts={summary.version === initialVersion ? initialPosts : undefined}
              initialTotal={summary.version === initialVersion ? initialTotal : undefined}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
