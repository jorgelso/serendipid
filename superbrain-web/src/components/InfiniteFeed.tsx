"use client";

import { useState } from "react";
import type { ClientPost } from "@/types/domain";
import PostCard from "./PostCard";
import MasonryGrid from "./MasonryGrid";

interface InfiniteFeedProps {
  initialPosts: ClientPost[];
  total: number;
  pageSize: number;
  // Extra query params (category/collection filters) forwarded to /api/feed
  // when loading further pages, so "Load more" respects active filters.
  params?: Record<string, string>;
}

export default function InfiniteFeed({ initialPosts, total, pageSize, params = {} }: InfiniteFeedProps) {
  const [posts, setPosts] = useState(initialPosts);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasMore = posts.length < total;

  async function loadMore() {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        offset: String(posts.length),
        limit: String(pageSize),
        ...params,
      });
      const res = await fetch(`/api/feed?${query.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't load more posts.");
      // The underlying export cache can be invalidated (reanalyze/mark-reviewed/
      // update-post/refresh) between the initial page load and a "load more"
      // click, shifting offsets — that can hand back a post already in `prev`.
      // Dedupe by shortcode so React never sees two siblings with the same key.
      setPosts((prev) => {
        const seen = new Set(prev.map((p) => p.shortcode));
        const fresh = (data.posts as ClientPost[]).filter((p) => !seen.has(p.shortcode));
        return [...prev, ...fresh];
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load more posts.");
    } finally {
      setLoading(false);
    }
  }

  if (posts.length === 0) {
    return (
      <p className="text-sm text-ink-muted py-10 text-center">Nothing here yet.</p>
    );
  }

  return (
    <div>
      <MasonryGrid>
        {posts.map((post) => (
          <PostCard key={post.shortcode} post={post} />
        ))}
      </MasonryGrid>

      {error && <p className="mt-4 text-sm text-danger text-center">{error}</p>}

      {hasMore && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loading}
            className="rounded-full bg-ink text-bg font-display font-semibold text-sm px-6 py-2.5 hover:opacity-85 transition-opacity disabled:opacity-50"
          >
            {loading ? "Loading…" : `Show more (${total - posts.length} left)`}
          </button>
        </div>
      )}
    </div>
  );
}
