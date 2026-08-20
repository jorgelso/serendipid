import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getCategories, getExport } from "@/lib/cache";
import { filterPosts, languageOptions, toDisplayPost, unionWithCanonicalCategories } from "@/lib/posts";
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
  // Set only when categoryMode is "exact" and that exact match came back
  // empty but a broader (union) match on the same categories wouldn't —
  // powers the "no exact matches, N posts include these categories
  // alongside others" hint. Null otherwise (including when exact match
  // already returned results — no need to nudge toward broadening).
  fallbackAnyCount: number | null;
}

async function loadBrowseData(
  category: string[],
  categoryMode: "exact" | "any",
  language: string,
  collectionId: string,
  sort: string,
  importance: number[]
): Promise<BrowseData> {
  const config = getConfig();
  const [{ posts, collections }, { canonical }] = await Promise.all([getExport(), getCategories()]);

  const baseOptions = {
    language: language || undefined,
    collectionId: collectionId || undefined,
    sort: (sort === "importance" ? "importance" : "recent") as "recent" | "importance",
    importance,
  };

  const filtered = filterPosts(posts, collections, {
    ...baseOptions,
    category: category.length > 0 ? category : undefined,
    categoryMatch: categoryMode,
  });

  let fallbackAnyCount: number | null = null;
  if (category.length > 0 && categoryMode === "exact" && filtered.length === 0) {
    const broader = filterPosts(posts, collections, {
      ...baseOptions,
      category,
      categoryMatch: "any",
    });
    if (broader.length > 0) fallbackAnyCount = broader.length;
  }

  return {
    posts: filtered.slice(0, PAGE_SIZE).map((p) => toDisplayPost(p, config.apiUrl)),
    total: filtered.length,
    categories: unionWithCanonicalCategories(posts, canonical),
    languages: languageOptions(posts),
    collections: collections.map((c) => ({ id: c.id, name: c.name })),
    fallbackAnyCount,
  };
}

export default async function BrowsePage(props: PageProps<"/browse">) {
  const searchParams = await props.searchParams;
  const categoryParam = typeof searchParams.category === "string" ? searchParams.category : "";
  const category = categoryParam ? categoryParam.split(",").filter(Boolean) : [];
  const categoryMode: "exact" | "any" =
    typeof searchParams.categoryMode === "string" && searchParams.categoryMode === "any" ? "any" : "exact";
  const language = typeof searchParams.language === "string" ? searchParams.language : "";
  const collection = typeof searchParams.collection === "string" ? searchParams.collection : "";
  const sort = typeof searchParams.sort === "string" ? searchParams.sort : "recent";
  const importanceParam = typeof searchParams.importance === "string" ? searchParams.importance : "";
  const importance = importanceParam
    .split(",")
    .map((v) => Number(v))
    .filter((v) => Number.isInteger(v) && v >= 1 && v <= 5);

  let data: BrowseData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadBrowseData(category, categoryMode, language, collection, sort, importance);
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
            categoryMode={categoryMode}
            language={language}
            collection={collection}
            sort={sort}
            importance={importance}
          />
        </div>
      )}

      {data && data.fallbackAnyCount != null && (
        <div className="mb-6 rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-ink-muted">
          No exact matches — {data.fallbackAnyCount} post{data.fallbackAnyCount === 1 ? "" : "s"} include{" "}
          {category.join(", ")} alongside other categories.{" "}
          <a
            href={`/browse?${new URLSearchParams({
              category: category.join(","),
              categoryMode: "any",
              ...(language ? { language } : {}),
              ...(collection ? { collection } : {}),
              ...(sort !== "recent" ? { sort } : {}),
              ...(importance.length > 0 ? { importance: importance.join(",") } : {}),
            }).toString()}`}
            className="font-bold text-coral-ink underline underline-offset-2 hover:opacity-80"
          >
            Show broader results
          </a>
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
          key={`${category.join(",")}|${categoryMode}|${language}|${collection}|${sort}|${importance.join(",")}`}
          initialPosts={data.posts}
          total={data.total}
          pageSize={PAGE_SIZE}
          params={{
            ...(category.length > 0 ? { category: category.join(",") } : {}),
            ...(category.length > 0 && categoryMode === "any" ? { categoryMode } : {}),
            ...(language ? { language } : {}),
            ...(collection ? { collection } : {}),
            ...(sort === "importance" ? { sort } : {}),
            ...(importance.length > 0 ? { importance: importance.join(",") } : {}),
          }}
        />
      )}
    </div>
  );
}
