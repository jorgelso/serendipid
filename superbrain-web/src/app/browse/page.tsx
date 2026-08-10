import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { categoryOptions, filterPosts, languageOptions, toDisplayPost } from "@/lib/posts";
import type { ClientPost } from "@/types/domain";
import BrowseFilters from "@/components/BrowseFilters";
import InfiniteFeed from "@/components/InfiniteFeed";

const PAGE_SIZE = 24;

interface BrowseData {
  posts: ClientPost[];
  total: number;
  categories: string[];
  languages: string[];
  collections: { id: string; name: string }[];
}

async function loadBrowseData(
  category: string,
  language: string,
  collectionId: string,
  sort: string
): Promise<BrowseData> {
  const config = getConfig();
  const { posts, collections } = await getExport();

  const filtered = filterPosts(posts, collections, {
    category: category || undefined,
    language: language || undefined,
    collectionId: collectionId || undefined,
    sort: sort === "importance" ? "importance" : "recent",
  });

  return {
    posts: filtered.slice(0, PAGE_SIZE).map((p) => toDisplayPost(p, config.apiUrl)),
    total: filtered.length,
    categories: categoryOptions(posts),
    languages: languageOptions(posts),
    collections: collections.map((c) => ({ id: c.id, name: c.name })),
  };
}

export default async function BrowsePage(props: PageProps<"/browse">) {
  const searchParams = await props.searchParams;
  const category = typeof searchParams.category === "string" ? searchParams.category : "";
  const language = typeof searchParams.language === "string" ? searchParams.language : "";
  const collection = typeof searchParams.collection === "string" ? searchParams.collection : "";
  const sort = typeof searchParams.sort === "string" ? searchParams.sort : "recent";

  let data: BrowseData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadBrowseData(category, language, collection, sort);
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your library.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Browse</h1>
        <p className="mt-1 text-ink-muted text-sm">Filter by category, language, or collection.</p>
      </div>

      {data && (
        <div className="mb-6">
          <BrowseFilters
            categories={data.categories}
            languages={data.languages}
            collections={data.collections}
            category={category}
            language={language}
            collection={collection}
            sort={sort}
          />
        </div>
      )}

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && (
        <InfiniteFeed
          // InfiniteFeed keeps its own "loaded posts" state client-side for
          // pagination — without a key tied to the active filters, React
          // treats it as the same component instance across a filter change
          // (same position in the tree) and keeps the OLD state instead of
          // picking up the new initialPosts prop, which is exactly the
          // "filter changes the URL but not what's shown" bug. The key
          // forces a remount whenever the filter combination changes.
          key={`${category}|${language}|${collection}|${sort}`}
          initialPosts={data.posts}
          total={data.total}
          pageSize={PAGE_SIZE}
          params={{
            ...(category ? { category } : {}),
            ...(language ? { language } : {}),
            ...(collection ? { collection } : {}),
            ...(sort === "importance" ? { sort } : {}),
          }}
        />
      )}
    </div>
  );
}
