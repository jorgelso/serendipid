import { fetchSemanticSearch, SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { mergeSearchHitsWithPosts } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import SearchBar from "@/components/SearchBar";
import SearchResultsWithStudyGuide from "@/components/SearchResultsWithStudyGuide";

async function loadResults(q: string): Promise<(ClientPost & { similarity: number })[]> {
  const config = getConfig();
  const [searchResponse, exportPayload] = await Promise.all([
    fetchSemanticSearch(q, 24, 0),
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
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Search</h1>
        <p className="mt-1 text-ink-muted text-sm">
          Find what you&rsquo;ve saved by meaning, not just keywords.
        </p>
      </div>

      <SearchBar defaultValue={q} />

      <div className="mt-8">
        {!q && (
          <p className="text-sm text-ink-muted py-10 text-center">
            Type an interest above — an instrument, a recipe, a mindset — and see what you&rsquo;ve
            already saved about it.
          </p>
        )}

        {q && (
          <p className="text-xs font-bold uppercase tracking-wide text-ink-muted mb-4">
            Results for &ldquo;{q}&rdquo;
          </p>
        )}

        {errorMessage && (
          <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
            {errorMessage}
          </div>
        )}

        {results && results.length === 0 && (
          <p className="text-sm text-ink-muted py-10 text-center">
            Nothing matched &ldquo;{q}&rdquo; closely enough. Try a broader phrase.
          </p>
        )}

        {results && results.length > 0 && <SearchResultsWithStudyGuide results={results} query={q} />}
      </div>
    </div>
  );
}
