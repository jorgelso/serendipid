"use client";

import { useEffect, useState } from "react";
import type { ClientPost, RecommendationStrategy } from "@/types/domain";
import MasonryGrid from "./MasonryGrid";
import PostCard from "./PostCard";

const STRATEGIES: { value: RecommendationStrategy; label: string }[] = [
  { value: "cluster", label: "By theme" },
  { value: "vector", label: "By similarity" },
  { value: "hybrid", label: "Hybrid" },
];

const RAIL_LIMIT = 12;

// Home's recommendation rail — a fixed-size, non-paginated section fed by
// src/lib/recommendations.ts's three scorers, with a visible switcher so the
// three can be compared live rather than shipping only the hybrid default.
export default function RecommendationsRail() {
  const [strategy, setStrategy] = useState<RecommendationStrategy>("hybrid");
  const [posts, setPosts] = useState<ClientPost[]>([]);
  const [coldStart, setColdStart] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Derived, not its own setState — "loading" is just "the strategy we last
  // fetched for hasn't caught up to the one currently selected yet". Avoids
  // an effect that unconditionally calls setState synchronously on every run.
  const [loadedStrategy, setLoadedStrategy] = useState<RecommendationStrategy | null>(null);
  const loading = loadedStrategy !== strategy;

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/recommendations?strategy=${strategy}&limit=${RAIL_LIMIT}`)
      .then(async (res) => {
        const data = await res.json();
        if (cancelled) return;
        if (!res.ok) throw new Error(data.error ?? "Couldn't load recommendations.");
        setPosts(data.posts ?? []);
        setColdStart(Boolean(data.coldStart));
        setError(null);
        setLoadedStrategy(strategy);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Couldn't load recommendations.");
        setLoadedStrategy(strategy);
      });

    return () => {
      cancelled = true;
    };
  }, [strategy]);

  return (
    <section className="mb-10">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display font-semibold text-xl">Recommended for you</h2>
        <div className="flex items-center gap-1.5 rounded-full border border-line bg-surface p-1">
          {STRATEGIES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setStrategy(s.value)}
              aria-pressed={strategy === s.value}
              className={`rounded-full text-[11px] font-bold px-3 py-1.5 transition-colors ${
                strategy === s.value ? "bg-ink text-bg" : "text-ink-muted hover:text-ink"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {coldStart && !loading && (
        <p className="mb-3 text-xs text-ink-muted">
          Not enough activity yet — showing your most important recent posts. Search, view, and rate a
          few posts to get real recommendations.
        </p>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      {loading ? (
        <p className="text-sm text-ink-muted py-6 text-center">Loading recommendations…</p>
      ) : posts.length === 0 ? (
        !error && <p className="text-sm text-ink-muted py-6 text-center">Nothing to recommend yet.</p>
      ) : (
        <MasonryGrid>
          {posts.map((post) => (
            <PostCard key={post.shortcode} post={post} />
          ))}
        </MasonryGrid>
      )}
    </section>
  );
}
