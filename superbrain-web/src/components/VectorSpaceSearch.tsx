"use client";

import { useRef, useState } from "react";

interface VectorSpaceSearchProps {
  // null = no active search (show everything at full brightness). query is
  // the submitted text that produced these shortcodes (empty string when
  // shortcodes is null) — the caller needs it as the study-guide
  // sourceLabel, the same way /search's page.tsx passes its `q` through to
  // SearchResultsWithStudyGuide.
  onResults: (shortcodes: Set<string> | null, query: string) => void;
}

// Free-text box that runs the same cosine-similarity search as /search
// (via /api/vector-space/search, which wraps the backend's
// /search/semantic) and reports the matched shortcodes back up so the
// scene can light them up — not a new cluster, just a transient highlight
// over whatever's already plotted, using the same dim-everything-else
// mechanism as clicking a theme in the legend.
//
// Fires only on explicit submit (Enter), not live-as-you-type — matching
// how /search's SearchBar waits for submit. Every submitted query now gets
// embedded and logged into search history for the Home recommendation
// engine (backend's search_queries table), so searching live on every
// keystroke would both spam that log with incomplete fragments ("c", "ca",
// "cat"...) and call the embedding API far more than necessary.
export default function VectorSpaceSearch({ onResults }: VectorSpaceSearchProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matchCount, setMatchCount] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  async function runSearch(query: string) {
    if (!query) {
      requestIdRef.current++; // invalidate any in-flight request
      setLoading(false);
      setError(null);
      setMatchCount(null);
      onResults(null, "");
      return;
    }

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/vector-space/search?q=${encodeURIComponent(query)}`);
      const data: { shortcodes?: string[]; error?: string } = await res.json();
      if (requestId !== requestIdRef.current) return; // a newer submit superseded this request

      if (!res.ok || data.error) {
        setError(data.error ?? "Search failed.");
        setMatchCount(null);
        onResults(null, "");
        return;
      }

      const shortcodes = data.shortcodes ?? [];
      setMatchCount(shortcodes.length);
      onResults(new Set(shortcodes), query);
    } catch {
      if (requestId !== requestIdRef.current) return;
      setError("Search failed.");
      setMatchCount(null);
      onResults(null, "");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    runSearch(value.trim());
  }

  function clear() {
    setValue("");
    requestIdRef.current++;
    setLoading(false);
    setError(null);
    setMatchCount(null);
    onResults(null, "");
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="pointer-events-auto flex w-72 items-center gap-2 rounded-2xl border border-line bg-surface/90 px-4 py-2.5 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md"
    >
      <span className="text-ink-muted" aria-hidden>
        ✦
      </span>
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Light up reels about… (press Enter)"
        className="min-w-0 flex-1 bg-transparent text-xs font-semibold text-ink placeholder:text-ink-muted placeholder:font-normal focus:outline-none"
      />
      {loading && <span className="text-ink-muted text-xs">…</span>}
      {!loading && value && (
        <button
          type="button"
          onClick={clear}
          aria-label="Clear search"
          className="text-ink-muted text-xs font-bold hover:text-ink"
        >
          ×
        </button>
      )}
      {!loading && !error && matchCount !== null && (
        <span className="shrink-0 text-ink-muted text-[11px]">{matchCount}</span>
      )}
      {error && <span className="shrink-0 text-[11px] text-coral-ink">{error}</span>}
    </form>
  );
}
