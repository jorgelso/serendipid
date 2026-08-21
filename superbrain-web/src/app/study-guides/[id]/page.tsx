import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchStudyGuide, fetchStudyGuideCollection, SuperBrainApiError } from "@/lib/apiClient";
import LazyPostList from "@/components/LazyPostList";
import DeleteStudyGuideButton from "@/components/DeleteStudyGuideButton";
import WashiTape from "@/components/WashiTape";
import { seededTapeColor } from "@/lib/collage";

const ROLE_LABEL: Record<string, string> = {
  final: "Final",
  full: "Full (all reels, one pass)",
  merge: "Merged (from chunks)",
  chunk: "Chunk",
};

export default async function StudyGuideDetailPage(props: PageProps<"/study-guides/[id]">) {
  const { id } = await props.params;

  let guide: Awaited<ReturnType<typeof fetchStudyGuide>>["data"] | null = null;
  let siblings: Awaited<ReturnType<typeof fetchStudyGuideCollection>>["data"]["guides"] | null = null;
  let errorMessage: string | null = null;

  try {
    ({ data: guide } = await fetchStudyGuide(id));
    if (guide.collection_id !== null) {
      const { data: collection } = await fetchStudyGuideCollection(guide.collection_id);
      siblings = collection.guides;
    }
  } catch (err) {
    if (err instanceof SuperBrainApiError && err.status === 404) {
      notFound();
    }
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading this study guide.";
  }

  return (
    <div className="mx-auto max-w-4xl px-5 py-8">
      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {guide && (
        <>
          <Link href="/study-guides" className="font-hand text-ink-muted hover:text-coral-ink mb-3 inline-block text-sm transition-colors">
            ← back to the corkboard
          </Link>

          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <p className="font-hand text-2xl leading-tight">{guide.title ?? "Untitled study guide"}</p>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-muted mt-1">
                {ROLE_LABEL[guide.role] ?? guide.role} · {guide.source_label ?? "Study guide"} ·{" "}
                {new Date(guide.created_at).toLocaleString()}
                {guide.model ? ` · ${guide.model}` : ""}
              </p>
              <p className="mt-1 text-xs text-ink-muted">
                {guide.shortcodes.length} source{guide.shortcodes.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <a
                href={`/api/study-guides/${guide.id}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-xs font-bold text-ink-muted hover:text-coral-ink transition-colors"
              >
                ↗ Open PDF
              </a>
              <DeleteStudyGuideButton id={guide.id} />
            </div>
          </div>

          {siblings && siblings.length > 1 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {siblings.map((s) => (
                <Link
                  key={s.id}
                  href={`/study-guides/${s.id}`}
                  className={`rounded-full border px-3 py-1 text-xs font-bold transition-colors ${
                    s.id === guide.id
                      ? "border-ink bg-ink text-bg"
                      : "border-line text-ink-muted hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  {ROLE_LABEL[s.role] ?? s.role}
                  {s.role === "chunk" ? ` ${siblings.filter((x) => x.role === "chunk").findIndex((x) => x.id === s.id) + 1}` : ""}
                </Link>
              ))}
            </div>
          )}

          <div className="relative rounded-3xl border border-line bg-surface overflow-hidden">
            <WashiTape color={seededTapeColor(guide.id)} rotation={-5} />
            <iframe
              src={`/api/study-guides/${guide.id}/pdf`}
              title={guide.title ?? "Study guide PDF"}
              className="h-[80vh] w-full"
            />
          </div>

          <div className="mt-6 rounded-2xl border border-line bg-surface px-4">
            <LazyPostList label="Sources" shortcodes={guide.shortcodes} />
          </div>

          {guide.excluded_shortcodes.length > 0 && (
            <div className="mt-2 rounded-2xl border border-line bg-surface px-4">
              <LazyPostList label="Excluded (low importance)" shortcodes={guide.excluded_shortcodes} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
