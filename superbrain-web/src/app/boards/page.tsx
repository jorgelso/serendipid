import { fetchBoards, SuperBrainApiError } from "@/lib/apiClient";
import CreateBoardForm from "@/components/CreateBoardForm";
import BoardCard from "@/components/BoardCard";
import ScrapbookPage from "@/components/ScrapbookPage";
import ScrapbookMasthead from "@/components/ScrapbookMasthead";
import WashiTape from "@/components/WashiTape";

export default async function BoardsPage() {
  let boards: Awaited<ReturnType<typeof fetchBoards>> = [];
  let errorMessage: string | null = null;

  try {
    boards = await fetchBoards();
  } catch (err) {
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your boards.";
  }

  return (
    <ScrapbookPage>
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-10">
        <ScrapbookMasthead
          words={["Boards"]}
          subtitle="Your own curated groupings of posts, separate from Instagram's saved collections. Each board can hold sub-collections for a second level of organization."
        />

        <div
          style={{ backgroundColor: "var(--paper-bg)" }}
          className="border-line relative z-10 mt-6 mb-8 max-w-md rounded-sm border p-4 shadow-[0_8px_16px_-8px_rgba(0,0,0,0.35)]"
        >
          <WashiTape color="sky" rotation={-5} />
          <p className="font-hand text-ink-muted mb-2 text-sm">pin a new board to the wall</p>
          <CreateBoardForm />
        </div>

        {errorMessage && (
          <div className="border-danger/30 bg-danger-soft text-coral-ink relative z-10 rounded-2xl border px-4 py-3 text-sm">
            {errorMessage}
          </div>
        )}

        {!errorMessage && boards.length === 0 && (
          <p className="font-hand text-ink-muted py-16 text-center text-lg">
            Nothing pinned up yet — create your first board above.
          </p>
        )}

        {!errorMessage && boards.length > 0 && (
          <div className="relative z-10 columns-1 gap-x-2 sm:columns-2 lg:columns-3 xl:columns-4">
            {boards.map((board, i) => (
              <BoardCard key={board.id} board={board} index={i} />
            ))}
          </div>
        )}
      </div>
    </ScrapbookPage>
  );
}
