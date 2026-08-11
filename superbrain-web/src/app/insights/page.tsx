import { SuperBrainApiError } from "@/lib/apiClient";
import { getCategories, getExport, getThemes } from "@/lib/cache";
import {
  computeCategoryCountsWithCanonical,
  computeLanguageCounts,
  computeTagCounts,
  groupShortcodesByCategory,
} from "@/lib/posts";
import type { Theme } from "@/types/domain";
import StatBars from "@/components/StatBars";
import ThemeAccordion from "@/components/ThemeAccordion";
import MoreSection from "@/components/MoreSection";

interface InsightsData {
  totalPosts: number;
  needsReviewCount: number;
  categoryCounts: [string, number][];
  languageCounts: [string, number][];
  tagCounts: [string, number][];
  themes: Theme[];
  groupedShortcodesByCategory: Record<string, string[]>;
}

async function loadInsightsData(): Promise<InsightsData> {
  const [{ posts }, { themes, unclusteredShortcodes }, { canonical }] = await Promise.all([
    getExport(),
    getThemes(),
    getCategories(),
  ]);

  const unclusteredSet = new Set(unclusteredShortcodes);
  const unclusteredLite = posts
    .filter((p) => unclusteredSet.has(p.shortcode))
    .map((p) => ({ shortcode: p.shortcode, category: p.category }));

  return {
    totalPosts: posts.length,
    needsReviewCount: posts.filter((p) => p.needs_review).length,
    categoryCounts: computeCategoryCountsWithCanonical(posts, canonical),
    languageCounts: computeLanguageCounts(posts),
    tagCounts: computeTagCounts(posts),
    themes,
    groupedShortcodesByCategory: groupShortcodesByCategory(unclusteredLite),
  };
}

export default async function InsightsPage() {
  let data: InsightsData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadInsightsData();
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your library.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Insights</h1>
        <p className="mt-1 text-ink-muted text-sm">
          What you&rsquo;ve saved, and the themes it noticed on its own.
        </p>
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && (
        <div className="space-y-10">
          {data.needsReviewCount > 0 && (
            <section className="rounded-2xl border border-yellow-ink/30 bg-yellow-soft p-5">
              <h2 className="font-display font-semibold text-lg text-yellow-ink mb-1">
                {data.needsReviewCount} of {data.totalPosts} posts need review
              </h2>
              <p className="text-sm text-yellow-ink/80">
                Categorized under an older version of the analysis pipeline. Open a post in Browse
                or Search and use &ldquo;Re-run analysis&rdquo; or &ldquo;Keep as is&rdquo; on it.
              </p>
            </section>
          )}

          <section className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-display font-semibold text-lg mb-1">{data.totalPosts} saved posts</h2>
            <p className="text-xs text-ink-muted mb-4">by category</p>
            <StatBars entries={data.categoryCounts} />
          </section>

          <section className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-display font-semibold text-lg mb-4">By language</h2>
            <StatBars entries={data.languageCounts} />
          </section>

          <section className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-display font-semibold text-lg mb-4">Most common tags</h2>
            <StatBars entries={data.tagCounts} />
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg mb-1">Themes it noticed</h2>
            <p className="text-xs text-ink-muted mb-4">
              Grouped automatically by comparing what each post is actually about — not just shared
              tags.
            </p>
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
            <div className="mt-4">
              <MoreSection groupedShortcodesByCategory={data.groupedShortcodesByCategory} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
