import { fetchSemanticSearch, SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { mergeSearchHitsWithPosts } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import SearchBar from "@/components/SearchBar";
import PostCard from "@/components/PostCard";

async function loadResults(q: string): Promise<(ClientPost & { similarity: number })[]> {
  const config = getConfig();
  const [searchResponse, exportPayload] = await Promise.all([
    fetchSemanticSearch(q, 20, 0),
    getExport(),
  ]);
  return mergeSearchHitsWithPosts(searchResponse.data, exportPayload.posts, config.apiUrl);
}

export default async function SearchPage(props: PageProps<"/search">) {
  const searchParams = await props.searchParams;
  const q = typeof searchParams.q === "string" ? searchParams.q.trim() : "";

  let results: (ClientPost & { similarity: number })[] | null = null;
  let errorMessage: string | null = null;

  if (q) {
    try {
      results = await loadResults(q);
    } catch (err) {
      errorMessage =
        err instanceof SuperBrainApiError ? err.message : "Something went wrong running that search.";
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <SearchBar defaultValue={q} />

      <div className="mt-8">
        {!q && (
          <p className="text-sm text-ink-muted">
            Type an interest above — an instrument, a recipe, a mindset — and see what you&rsquo;ve
            already saved about it.
          </p>
        )}

        {q && (
          <p className="font-label text-[11px] uppercase tracking-wide text-ink-muted mb-4">
            Looking up &ldquo;{q}&rdquo;
          </p>
        )}

        {errorMessage && (
          <div className="rounded-md border border-danger/40 bg-rust-soft px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        {results && results.length === 0 && (
          <p className="text-sm text-ink-muted">
            Nothing matched &ldquo;{q}&rdquo; closely enough. Try a broader phrase.
          </p>
        )}

        {results && results.length > 0 && (
          <div className="space-y-3">
            {results.map((post) => (
              <PostCard key={post.shortcode} post={post} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
