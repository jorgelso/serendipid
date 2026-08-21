import { fetchStudyGuideCollections, SuperBrainApiError } from "@/lib/apiClient";
import type { StudyGuideCollection } from "@/types/domain";
import ScrapbookPage from "@/components/ScrapbookPage";
import ScrapbookMasthead from "@/components/ScrapbookMasthead";
import StudyGuideCorkboard from "@/components/StudyGuideCorkboard";

export default async function StudyGuidesPage() {
  let collections: StudyGuideCollection[] | null = null;
  let errorMessage: string | null = null;

  try {
    ({ data: collections } = await fetchStudyGuideCollections());
  } catch (err) {
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading study guides.";
  }

  return (
    <ScrapbookPage>
      <div className="mx-auto max-w-7xl px-5 py-8 sm:px-10">
        <ScrapbookMasthead subtitle="Distilled docs generated from a selection, search result, theme, idea, or 3D-space picks. Every generation is a pile you can dig through, rendered as real PDFs." />

        {errorMessage && (
          <div className="border-danger/30 bg-danger-soft text-coral-ink relative z-10 mb-6 rounded-2xl border px-4 py-3 text-sm">
            {errorMessage}
          </div>
        )}

        {collections && <StudyGuideCorkboard initialCollections={collections} />}
      </div>
    </ScrapbookPage>
  );
}
