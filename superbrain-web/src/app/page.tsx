import { SuperBrainApiError } from "@/lib/apiClient";
import { getCacheTimestamps, getExport } from "@/lib/cache";
import { sortPostsByRecency, toDisplayPost } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import InfiniteFeed from "@/components/InfiniteFeed";
import RecommendationsRail from "@/components/RecommendationsRail";

const PAGE_SIZE = 24;

interface Feed {
  posts: ClientPost[];
  total: number;
  fetchedAt: string | null;
}

async function loadInitialFeed(): Promise<Feed> {
  const { posts } = await getExport();
  const sorted = sortPostsByRecency(posts);
  return {
    posts: sorted.slice(0, PAGE_SIZE).map((p) => toDisplayPost(p)),
    total: sorted.length,
    fetchedAt: getCacheTimestamps().exportFetchedAt,
  };
}

export default async function HomePage() {
  let feed: Feed | null = null;
  let errorMessage: string | null = null;

  try {
    feed = await loadInitialFeed();
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your feed.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Your feed</h1>
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      <RecommendationsRail />

      {feed && (
        <InfiniteFeed
          // Keyed on the cache's fetch timestamp so clicking "Rescan library"
          // (router.refresh()) forces a remount instead of leaving the old
          // client-side pagination state in place — see the identical fix
          // and explanation in app/browse/page.tsx.
          key={feed.fetchedAt ?? "initial"}
          initialPosts={feed.posts}
          total={feed.total}
          pageSize={PAGE_SIZE}
        />
      )}
    </div>
  );
}
