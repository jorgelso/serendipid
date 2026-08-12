import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { filterPosts, toDisplayPost } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import EloquenceFilters from "@/components/EloquenceFilters";
import InfiniteFeed from "@/components/InfiniteFeed";

const PAGE_SIZE = 24;

interface EloquentData {
  posts: ClientPost[];
  total: number;
}

async function loadEloquentData(tutorial: "" | "yes" | "no"): Promise<EloquentData> {
  const config = getConfig();
  const { posts } = await getExport();

  const filtered = filterPosts(posts, [], {
    sort: "recent",
    eloquent: true,
    tutorial: tutorial || undefined,
  });

  return {
    posts: filtered.slice(0, PAGE_SIZE).map((p) => toDisplayPost(p, config.apiUrl)),
    total: filtered.length,
  };
}

export default async function EloquentPage(props: PageProps<"/eloquent">) {
  const searchParams = await props.searchParams;
  const tutorialParam = typeof searchParams.tutorial === "string" ? searchParams.tutorial : "";
  const tutorial = tutorialParam === "yes" || tutorialParam === "no" ? tutorialParam : "";

  let data: EloquentData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadEloquentData(tutorial);
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading eloquent posts.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Eloquent</h1>
        <p className="mt-1 text-ink-muted text-sm">
          Posts judged eloquent in the oratory sense — clear, well-spoken, and rhetorically skilled,
          independent of topic. Filter between speeches/commentary and tutorial-style delivery.
        </p>
      </div>

      <div className="mb-6">
        <EloquenceFilters tutorial={tutorial} />
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && data.total === 0 && (
        <p className="text-sm text-ink-muted py-10 text-center">
          No eloquent posts found for this filter yet.
        </p>
      )}

      {data && data.total > 0 && (
        <InfiniteFeed
          // Same remount-on-filter-change trick as /browse — see its comment.
          key={`eloquent|${tutorial}`}
          initialPosts={data.posts}
          total={data.total}
          pageSize={PAGE_SIZE}
          params={{
            eloquent: "true",
            ...(tutorial ? { tutorial } : {}),
          }}
        />
      )}
    </div>
  );
}
