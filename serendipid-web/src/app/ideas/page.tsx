import Link from "next/link";
import { SerendipidApiError } from "@/lib/apiClient";
import { getIdeas, getThemes } from "@/lib/cache";
import type { Idea } from "@/types/domain";
import IdeaRow from "@/components/IdeaRow";

interface IdeasData {
  ideas: Idea[];
  themeLabel: string | null;
}

async function loadIdeas(themeId?: string): Promise<IdeasData> {
  const ideas = await getIdeas(themeId);
  let themeLabel: string | null = null;
  if (themeId) {
    const { themes } = await getThemes();
    themeLabel = themes.find((t) => t.id === themeId)?.label ?? null;
  }
  return { ideas, themeLabel };
}

export default async function IdeasPage(props: PageProps<"/ideas">) {
  const searchParams = await props.searchParams;
  const themeId = typeof searchParams.themeId === "string" ? searchParams.themeId : undefined;

  let data: IdeasData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadIdeas(themeId);
  } catch (err) {
    errorMessage = err instanceof SerendipidApiError ? err.message : "Something went wrong loading ideas.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Ideas</h1>
        <p className="mt-1 text-ink-muted text-sm">
          {themeId
            ? `Recurring tags within "${data?.themeLabel ?? "this theme"}", ranked by how many saved posts repeat them.`
            : "Tags that recur across your whole library, ranked by how many saved posts repeat them."}
        </p>
        <p className="mt-1 text-ink-muted text-xs italic">
          v1: counted from stored tags, not real semantic dedup yet — two posts making the same point in
          different words won&rsquo;t be merged here. Low-value posts are already excluded.
        </p>
        {themeId && (
          <Link
            href="/ideas"
            className="mt-2 inline-block text-xs text-ink-muted hover:text-coral-ink transition-colors"
          >
            ← View across whole library
          </Link>
        )}
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {data && data.ideas.length === 0 && (
        <p className="text-sm text-ink-muted py-10 text-center">
          No recurring ideas found yet — an idea needs at least two posts sharing a tag to show up here.
        </p>
      )}

      {data && data.ideas.length > 0 && (
        <div className="space-y-2">
          {data.ideas.map((idea) => (
            <IdeaRow key={idea.tag} idea={idea} />
          ))}
        </div>
      )}
    </div>
  );
}
