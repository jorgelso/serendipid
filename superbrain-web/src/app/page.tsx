import { SuperBrainApiError } from "@/lib/apiClient";
import { getExport, getThemes } from "@/lib/cache";
import { groupShortcodesByCategory } from "@/lib/posts";
import type { Theme } from "@/types/domain";
import SearchBar from "@/components/SearchBar";
import RefreshButton from "@/components/RefreshButton";
import ThemeAccordion from "@/components/ThemeAccordion";
import MoreSection from "@/components/MoreSection";

interface HomeData {
  themes: Theme[];
  groupedShortcodesByCategory: Record<string, string[]>;
}

// Deliberately lightweight: only labels, counts, and shortcodes are computed
// here. Full post data (including often-large thumbnails) is fetched on
// demand by LazyPostList when a theme/category is actually expanded, so this
// page's payload stays small regardless of how many posts are in the library.
async function loadHomeData(): Promise<HomeData> {
  const [{ posts }, { themes, unclusteredShortcodes }] = await Promise.all([
    getExport(),
    getThemes(),
  ]);

  const unclusteredSet = new Set(unclusteredShortcodes);
  const unclusteredLite = posts
    .filter((p) => unclusteredSet.has(p.shortcode))
    .map((p) => ({ shortcode: p.shortcode, category: p.category }));

  return { themes, groupedShortcodesByCategory: groupShortcodesByCategory(unclusteredLite) };
}

export default async function HomePage() {
  let data: HomeData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadHomeData();
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your library.";
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="font-display text-2xl leading-snug max-w-2xl">
        Your saved reels, catalogued by what they&rsquo;re actually about — not just the tags you
        gave them.
      </p>

      <div className="mt-8 flex items-start justify-between gap-4">
        <div className="flex-1">
          <SearchBar />
        </div>
        <RefreshButton />
      </div>

      <div className="mt-10">
        {errorMessage && (
          <div className="rounded-md border border-danger/40 bg-rust-soft px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        {data && (
          <>
            {data.themes.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No themes yet — as more of your saved reels get analyzed, related ones will start
                grouping here on their own.
              </p>
            ) : (
              <div className="space-y-3">
                {data.themes.map((theme) => (
                  <ThemeAccordion key={theme.id} theme={theme} />
                ))}
              </div>
            )}

            <div className="mt-6">
              <MoreSection groupedShortcodesByCategory={data.groupedShortcodesByCategory} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
