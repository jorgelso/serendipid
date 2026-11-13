"use client";

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";

export interface LightPost {
  shortcode: string;
  title: string | null;
  username: string;
  should_revisit: boolean;
}

interface PostPickerProps {
  title: string;
  allPosts: LightPost[];
  excludeShortcodes: string[];
  onAdd: (shortcode: string) => Promise<void>;
  onClose: () => void;
}

const MAX_RESULTS = 40;

// A lightweight text-search picker (title/username substring match over the
// already-fetched full post list — no new backend search endpoint) used to
// add existing posts into a board or sub-collection from /boards/[boardId].
export default function PostPicker({ title, allPosts, excludeShortcodes, onAdd, onClose }: PostPickerProps) {
  const [query, setQuery] = useState("");
  const [addingShortcode, setAddingShortcode] = useState<string | null>(null);
  const excluded = useMemo(() => new Set(excludeShortcodes), [excludeShortcodes]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const candidates = allPosts.filter((p) => !excluded.has(p.shortcode));
    if (!q) return candidates.slice(0, MAX_RESULTS);
    return candidates
      .filter((p) => (p.title ?? "").toLowerCase().includes(q) || p.username.toLowerCase().includes(q))
      .slice(0, MAX_RESULTS);
  }, [allPosts, excluded, query]);

  async function handleAdd(shortcode: string) {
    setAddingShortcode(shortcode);
    try {
      await onAdd(shortcode);
    } finally {
      setAddingShortcode(null);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-display font-semibold text-lg">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-full w-8 h-8 flex items-center justify-center hover:bg-surface-2 text-lg"
          >
            ×
          </button>
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by title or @username…"
          autoFocus
          className="mt-3 w-full rounded-full border border-line bg-bg px-4 py-2.5 text-sm"
        />

        <div className="mt-3 flex-1 overflow-y-auto flex flex-col gap-1">
          {results.length === 0 && <p className="text-sm text-ink-muted px-1">No matching posts.</p>}
          {results.map((post) => (
            <button
              key={post.shortcode}
              type="button"
              disabled={addingShortcode === post.shortcode}
              onClick={() => handleAdd(post.shortcode)}
              className="text-left flex items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface-2 transition-colors disabled:opacity-50"
            >
              <span className="min-w-0 truncate text-sm">
                {post.title || "Untitled reel"}{" "}
                <span className="text-ink-muted">@{post.username}</span>
              </span>
              <span className="shrink-0 text-xs font-bold text-coral-ink">
                {addingShortcode === post.shortcode ? "Adding…" : "+ Add"}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
