import { SerendipidApiError } from "@/lib/apiClient";
import { getCategories, getChangelog, getExport } from "@/lib/cache";
import { languageOptions, sortPostsByRecency, toDisplayPost, unionWithCanonicalCategories, versionSummaries } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import type { VersionSummary } from "@/lib/posts";
import VersionPager from "@/components/VersionPager";

const PAGE_SIZE = 24;

interface VersionsData {
  summaries: VersionSummary[];
  initialVersion: number;
  initialPosts: ClientPost[];
  initialTotal: number;
  categories: string[];
  languages: string[];
}

async function loadVersionsData(): Promise<VersionsData> {
  const [{ posts }, changelog, { canonical }] = await Promise.all([
    getExport(),
    getChangelog(),
    getCategories(),
  ]);

  const summaries = versionSummaries(posts, changelog);
  const categories = unionWithCanonicalCategories(posts, canonical);
  const languages = languageOptions(posts);

  if (summaries.length === 0) {
    return { summaries, initialVersion: 0, initialPosts: [], initialTotal: 0, categories, languages };
  }

  // Deliberately only the FIRST (oldest) panel's posts are sent in the
  // initial server render — shipping every version's full post data
  // (thumbnails included, some as inlined base64 data: URIs) in one SSR
  // payload would balloon it the same way /space's initial design did
  // before its thumbnail-proxying fix. Every other panel fetches its own
  // first page lazily via /api/versions/feed once it becomes active.
  const initialVersion = summaries[0].version;
  const versionPosts = sortPostsByRecency(posts.filter((p) => p.analysis_version === initialVersion));

  return {
    summaries,
    initialVersion,
    initialPosts: versionPosts.slice(0, PAGE_SIZE).map((p) => toDisplayPost(p)),
    initialTotal: versionPosts.length,
    categories,
    languages,
  };
}

export default async function VersionsPage() {
  let data: VersionsData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadVersionsData();
  } catch (err) {
    errorMessage =
      err instanceof SerendipidApiError ? err.message : "Something went wrong loading your library.";
  }

  return (
    <div className="h-[calc(100dvh-70px)] flex flex-col">
      {errorMessage && (
        <div className="mx-auto max-w-6xl w-full px-5 py-4">
          <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
            {errorMessage}
          </div>
        </div>
      )}

      {data && data.summaries.length === 0 && (
        <div className="mx-auto max-w-6xl w-full px-5 py-10 text-center text-ink-muted text-sm">
          Nothing to review — every saved reel is on the latest pipeline version.
        </div>
      )}

      {data && data.summaries.length > 0 && (
        <VersionPager
          summaries={data.summaries}
          initialVersion={data.initialVersion}
          initialPosts={data.initialPosts}
          initialTotal={data.initialTotal}
          categories={data.categories}
          languages={data.languages}
        />
      )}
    </div>
  );
}
