"use client";

import { useState } from "react";
import type { ClientPost } from "@/types/domain";
import { TagChips } from "./Chips";
import PostCard from "./PostCard";

interface LazyPostListProps {
  label: string;
  subLabels?: string[];
  shortcodes: string[];
  variant?: "micro" | "category";
}

// Renders a row (label + count) that fetches and reveals its posts only when
// clicked — this is what keeps the initial page small: the posts themselves
// (with their often-large base64 thumbnails) never enter the HTML until a
// person actually asks to see them.
export default function LazyPostList({ label, subLabels, shortcodes, variant = "micro" }: LazyPostListProps) {
  const [open, setOpen] = useState(false);
  const [posts, setPosts] = useState<ClientPost[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (posts || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/posts?shortcodes=${encodeURIComponent(shortcodes.join(","))}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to load posts.");
      setPosts(data.posts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load posts.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={open}
        className="w-full flex items-center gap-2 py-1.5 text-left"
      >
        <span
          aria-hidden
          className={`text-ink-muted text-xs transition-transform ${open ? "rotate-90" : ""} ${
            variant === "category" ? "text-ink-muted" : ""
          }`}
        >
          &#9656;
        </span>
        <span className={variant === "category" ? "font-label text-[11px] uppercase tracking-wide text-ink-muted" : "font-body font-medium text-sm"}>
          {label}
        </span>
        {subLabels && <TagChips tags={subLabels} />}
        <span className="ml-auto font-label text-[11px] text-ink-muted">{shortcodes.length}</span>
      </button>
      {open && (
        <div className="mt-2 mb-1 space-y-3 pl-5">
          {loading && <p className="text-xs text-ink-muted">Loading…</p>}
          {error && <p className="text-xs text-danger">{error}</p>}
          {posts?.map((post) => (
            <PostCard key={post.shortcode} post={post} />
          ))}
        </div>
      )}
    </div>
  );
}
