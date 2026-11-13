"use client";

import { useEffect, useRef, useState } from "react";
import type { ClientPost } from "@/types/domain";
import type { VersionFilters, VersionSummary } from "@/lib/posts";
import { useBulkRescanProgress } from "@/lib/useBulkRescanProgress";
import MasonryGrid from "./MasonryGrid";
import PostCard from "./PostCard";
import ConfirmDialog from "./ConfirmDialog";

const PAGE_SIZE = 24;

interface VersionPanelProps {
  summary: VersionSummary;
  filters: VersionFilters;
  isActive: boolean;
  initialPosts?: ClientPost[];
  initialTotal?: number;
}

function filterKey(filters: VersionFilters): string {
  return `${filters.category}|${filters.language}|${filters.sort}`;
}

// One full-screen panel in VersionPager's horizontal scroll-snap track: a
// header (changelog context + "Rescan entire version") and its own
// independently vertically-scrolling, auto-load-on-scroll grid — the
// version-scoped analog of InfiniteFeed, but paginating within one
// analysis_version instead of the whole library, and loading on scroll
// instead of a "Load more" click.
export default function VersionPanel({ summary, filters, isActive, initialPosts, initialTotal }: VersionPanelProps) {
  const [posts, setPosts] = useState<ClientPost[]>(initialPosts ?? []);
  const [total, setTotal] = useState(initialTotal ?? summary.count);
  const [loadedFilterKey, setLoadedFilterKey] = useState<string | null>(
    initialPosts ? filterKey(filters) : null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [confirming, setConfirming] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [queuedShortcodes, setQueuedShortcodes] = useState<string[]>([]);
  const [rescoredCount, setRescoredCount] = useState(0);

  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);

  const { pending } = useBulkRescanProgress(queuedShortcodes);

  async function fetchPage(offset: number) {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        version: String(summary.version),
        offset: String(offset),
        limit: String(PAGE_SIZE),
      });
      if (filters.category) query.set("category", filters.category);
      if (filters.language) query.set("language", filters.language);
      if (filters.sort === "importance") query.set("sort", filters.sort);

      const res = await fetch(`/api/versions/feed?${query.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't load this version's reels.");

      setTotal(data.total);
      setPosts((prev) => {
        if (offset === 0) return data.posts;
        const seen = new Set(prev.map((p) => p.shortcode));
        const fresh = (data.posts as ClientPost[]).filter((p) => !seen.has(p.shortcode));
        return [...prev, ...fresh];
      });
      setLoadedFilterKey(filterKey(filters));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load this version's reels.");
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }

  // Fetch page 0 the first time this panel becomes active under the current
  // filters. Panels stay mounted the whole time (scroll-snap, not
  // unmount/remount on switch), so a filter change while this panel is
  // inactive is simply picked up the next time it's revisited rather than
  // every panel refetching on every filter toggle.
  //
  // The fetch is kicked off via a resolved-promise microtask rather than
  // called directly in the effect body — fetchPage sets loading/error state
  // before its first `await`, and calling it synchronously here would run
  // that setState during the effect's own execution (flagged by
  // react-hooks/set-state-in-effect). Deferring one microtask moves it
  // outside the effect's synchronous call frame with no perceptible delay.
  useEffect(() => {
    if (!isActive) return;
    if (loadedFilterKey === filterKey(filters)) return;
    Promise.resolve().then(() => fetchPage(0));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, filters.category, filters.language, filters.sort]);

  // Auto-load more as the user scrolls near the bottom of this panel's own
  // scroll container — no "Load more" click, per the spec.
  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && posts.length < total && !loadingRef.current) {
          fetchPage(posts.length);
        }
      },
      { root, rootMargin: "600px" }
    );
    io.observe(sentinel);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posts.length, total]);

  async function handleConfirmBulkRescan() {
    setBulkBusy(true);
    setBulkError(null);
    try {
      const res = await fetch("/api/reanalyze/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcodes: summary.shortcodes }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't start the rescan.");

      setQueuedShortcodes(data.queued ?? []);
      setRescoredCount((data.rescored ?? []).length);
      // Every targeted shortcode is now either already re-scored onto a
      // newer version (the version-7 cheap path) or hard-deleted pending a
      // full re-analysis — either way, none of them belong in this panel
      // anymore.
      setPosts([]);
      setTotal(0);
      setConfirming(false);
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Couldn't start the rescan.");
    } finally {
      setBulkBusy(false);
    }
  }

  const rescanning = queuedShortcodes.length > 0;
  const finishedCount = queuedShortcodes.length - pending.length;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 pt-4 pb-3 border-b border-line">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display font-semibold text-lg">
              Version {summary.version}
              {summary.isCurrent && (
                <span className="ml-2 align-middle rounded-full bg-mint-soft text-mint-ink text-[11px] font-bold px-2 py-0.5">
                  current
                </span>
              )}
            </h2>
            {summary.changelogTitle && (
              <p className="mt-0.5 text-sm font-bold text-ink-muted">{summary.changelogTitle}</p>
            )}
            {summary.changelogDescription && (
              <p className="mt-0.5 text-xs text-ink-muted max-w-2xl">{summary.changelogDescription}</p>
            )}
            <p className="mt-1 text-xs text-ink-muted">
              {total} reel{total === 1 ? "" : "s"}
            </p>
          </div>

          {!summary.isCurrent && !rescanning && (
            <button
              onClick={() => setConfirming(true)}
              className="shrink-0 rounded-full bg-yellow-ink text-bg text-xs font-bold px-3.5 py-2 hover:opacity-85 transition-opacity"
            >
              Rescan entire version
            </button>
          )}
        </div>

        {rescanning && (
          <div className="mt-3 rounded-xl bg-yellow-soft px-3 py-2 text-xs font-bold text-yellow-ink">
            Rescanning {queuedShortcodes.length} reel{queuedShortcodes.length === 1 ? "" : "s"}
            {rescoredCount > 0 ? ` (+${rescoredCount} fixed instantly)` : ""} — {finishedCount} of{" "}
            {queuedShortcodes.length} done so far. This can take a while — reels are processed one at a
            time, or (if batch mode is enabled on the backend) as a single shared job that may take up to
            24 hours; check back later.
          </div>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 pb-8 pt-4">
        {posts.length === 0 && !loading ? (
          <p className="text-sm text-ink-muted py-10 text-center">
            {rescanning ? "Rescan in progress — nothing left here for now." : "Nothing here yet."}
          </p>
        ) : (
          <MasonryGrid>
            {posts.map((post) => (
              <PostCard key={post.shortcode} post={post} rescanMode={summary.version === 7 ? "cheap" : "full"} />
            ))}
          </MasonryGrid>
        )}

        {error && <p className="mt-4 text-sm text-danger text-center">{error}</p>}
        {loading && <p className="mt-4 text-sm text-ink-muted text-center">Loading…</p>}

        <div ref={sentinelRef} className="h-1" />
      </div>

      {confirming && (
        <ConfirmDialog
          title={`Rescan all of version ${summary.version}?`}
          message={
            `This will reprocess ${summary.shortcodes.length} reel${
              summary.shortcodes.length === 1 ? "" : "s"
            } using their already-downloaded media where possible — nothing is re-downloaded from ` +
            `Instagram unless a reel's media is missing locally, and nothing is deleted until the ` +
            `rescan actually succeeds. They'll disappear from your feed until each one finishes; ` +
            `depending on how the backend is configured this can take a while (processed one at a ` +
            `time) or run as a single shared batch job that may take up to 24 hours.` +
            (bulkError ? `\n\n${bulkError}` : "")
          }
          confirmLabel={bulkBusy ? "Starting…" : "Rescan all"}
          busy={bulkBusy}
          onConfirm={handleConfirmBulkRescan}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
