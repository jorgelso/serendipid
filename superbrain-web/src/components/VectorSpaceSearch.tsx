"use client";

import { useEffect, useRef, useState } from "react";

interface VectorSpaceSearchProps {
  // null = no active search (show everything at full brightness).
  onResults: (shortcodes: Set<string> | null) => void;
}

const DEBOUNCE_MS = 350;

// Free-text box that runs the same cosine-similarity search as /search
// (via /api/vector-space/search, which wraps the backend's
// /search/semantic) and reports the matched shortcodes back up so the
// scene can light them up — not a new cluster, just a transient highlight
// over whatever's already plotted, using the same dim-everything-else
// mechanism as clicking a theme in the legend.
export default function VectorSpaceSearch({ onResults }: VectorSpaceSearchProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matchCount, setMatchCount] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const query = value.trim();
    if (!query) {
      requestIdRef.current++; // invalidate any in-flight request
      Promise.resolve().then(() => {
        setLoading(false);
        setError(null);
        setMatchCount(null);
        onResults(null);
      });
      return;
    }

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/vector-space/search?q=${encodeURIComponent(query)}`);
        const data: { shortcodes?: string[]; error?: string } = await res.json();
        if (requestId !== requestIdRef.current) return; // a newer keystroke superseded this request

        if (!res.ok || data.error) {
          setError(data.error ?? "Search failed.");
          setMatchCount(null);
          onResults(null);
          return;
        }

        const shortcodes = data.shortcodes ?? [];
        setMatchCount(shortcodes.length);
        onResults(new Set(shortcodes));
      } catch {
        if (requestId !== requestIdRef.current) return;
        setError("Search failed.");
        setMatchCount(null);
        onResults(null);
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onResults is a state setter passed from the parent, stable enough not to re-trigger the debounce
  }, [value]);

  function clear() {
    setValue("");
    setError(null);
    setMatchCount(null);
    onResults(null);
  }

  return (
    <div className="pointer-events-auto flex w-72 items-center gap-2 rounded-2xl border border-line bg-surface/90 px-4 py-2.5 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
      <span className="text-ink-muted" aria-hidden>
        ✦
      </span>
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Light up reels about…"
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
    </div>
  );
}
