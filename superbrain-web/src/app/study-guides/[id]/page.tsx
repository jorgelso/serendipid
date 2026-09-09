import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchStudyGuide, fetchStudyGuideCollection, markStudyGuideCollectionOpened, SuperBrainApiError } from "@/lib/apiClient";
import LazyPostList from "@/components/LazyPostList";
import DeleteStudyGuideButton from "@/components/DeleteStudyGuideButton";
import WashiTape from "@/components/WashiTape";
import PushPin from "@/components/PushPin";
import CutoutChip from "@/components/CutoutChip";
import TypewriterTag from "@/components/TypewriterTag";
import StickerLabel from "@/components/StickerLabel";
import ScrapbookPage from "@/components/ScrapbookPage";
import { seededRotation, seededTapeColor } from "@/lib/collage";

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
      // Best-effort — this is only a recommendation signal, must never
      // block or break the page render.
      markStudyGuideCollectionOpened(guide.collection_id).catch(() => {});
    }
  } catch (err) {
    if (err instanceof SuperBrainApiError && err.status === 404) {
      notFound();
    }
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading this study guide.";
  }

  return (
    <ScrapbookPage>
      <div className="mx-auto max-w-4xl px-5 py-8 sm:px-10">
        <Link
          href="/study-guides"
          className="font-hand text-ink-muted hover:text-coral-ink relative z-10 mb-6 inline-block text-sm transition-colors"
        >
          ← back to the corkboard
        </Link>

        {errorMessage && (
          <div className="border-danger/30 bg-danger-soft text-coral-ink relative z-10 mb-6 rounded-2xl border px-4 py-3 text-sm">
            {errorMessage}
          </div>
        )}

        {guide && (
          <>
            {/* Title + metadata — a cutout headline chip with a typewritten strip beneath it, same materials as the corkboard cards */}
            <div className="relative z-10 mb-6 flex flex-wrap items-end gap-3">
              <CutoutChip seed={guide.id} size="md" rotationRange={4} className="max-w-full text-xl">
                {guide.title ?? "Untitled study guide"}
              </CutoutChip>
              <div style={{ transform: `rotate(${seededRotation(guide.id + 4, 3)}deg)` }}>
                <TypewriterTag>
                  {ROLE_LABEL[guide.role] ?? guide.role} · {guide.source_label ?? "Study guide"} ·{" "}
                  {new Date(guide.created_at).toLocaleDateString()}
                  {guide.model ? ` · ${guide.model}` : ""}
                </TypewriterTag>
              </div>
            </div>

            {/* Sibling chips + actions — sticker tabs to jump between a generation's guides, plus the raw-pdf/delete escape hatches */}
            <div className="relative z-10 mb-8 flex flex-wrap items-center gap-2">
              {siblings &&
                siblings.length > 1 &&
                siblings.map((s) => {
                  const isCurrent = s.id === guide.id;
                  const color = seededTapeColor(s.id);
                  const chunkIndex =
                    s.role === "chunk" ? siblings!.filter((x) => x.role === "chunk").findIndex((x) => x.id === s.id) + 1 : null;
                  return (
                    <Link key={s.id} href={`/study-guides/${s.id}`} className="relative inline-block">
                      {isCurrent && <PushPin color={`var(--color-${color})`} />}
                      <StickerLabel
                        color={color}
                        rotation={seededRotation(s.id, 4)}
                        className={isCurrent ? "ring-ink/60 ring-2" : "opacity-60 transition-opacity hover:opacity-100"}
                      >
                        {ROLE_LABEL[s.role] ?? s.role}
                        {chunkIndex ? ` ${chunkIndex}` : ""}
                      </StickerLabel>
                    </Link>
                  );
                })}

              <span className="font-hand text-ink-muted ml-auto text-xs">
                {guide.shortcodes.length} source{guide.shortcodes.length === 1 ? "" : "s"}
              </span>
              <a
                href={`/api/study-guides/${guide.id}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="font-hand text-ink-muted hover:text-coral-ink shrink-0 text-xs font-bold transition-colors"
              >
                ↗ raw pdf
              </a>
              <DeleteStudyGuideButton id={guide.id} />
            </div>

            {/* The guide itself, pinned up like a photocopy rather than framed as an app window — the browser's native PDF toolbar/sidebar is suppressed via the URL fragment so it reads as a document, not a viewer chrome */}
            <div className="relative z-10 mx-auto mb-8 max-w-3xl">
              <div className="relative bg-white p-3 pb-5 shadow-[0_20px_36px_-18px_rgba(0,0,0,0.55)]">
                <PushPin color={`var(--color-${seededTapeColor(guide.id)})`} />
                <WashiTape color={seededTapeColor(guide.id + 2)} rotation={seededRotation(guide.id + 2, 8)} />
                <iframe
                  src={`/api/study-guides/${guide.id}/pdf#toolbar=0&navpanes=0&scrollbar=0`}
                  title={guide.title ?? "Study guide PDF"}
                  className="h-[75vh] w-full border-0"
                />
              </div>
            </div>

            <div
              style={{ transform: `rotate(${seededRotation(guide.id + 6, 1)}deg)`, backgroundColor: "var(--paper-bg)" }}
              className="border-line relative z-10 mb-3 rounded-[2px] border px-4 shadow-[0_10px_20px_-14px_rgba(0,0,0,0.4)]"
            >
              <LazyPostList label="Sources" shortcodes={guide.shortcodes} />
            </div>

            {guide.excluded_shortcodes.length > 0 && (
              <div
                style={{ transform: `rotate(${seededRotation(guide.id + 8, 1)}deg)`, backgroundColor: "var(--paper-bg)" }}
                className="border-line relative z-10 rounded-[2px] border px-4 shadow-[0_10px_20px_-14px_rgba(0,0,0,0.4)]"
              >
                <LazyPostList label="Excluded (low importance)" shortcodes={guide.excluded_shortcodes} />
              </div>
            )}
          </>
        )}
      </div>
    </ScrapbookPage>
  );
}
