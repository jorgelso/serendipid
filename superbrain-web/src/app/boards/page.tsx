import { fetchBoards, SuperBrainApiError } from "@/lib/apiClient";
import CreateBoardForm from "@/components/CreateBoardForm";
import BoardCard from "@/components/BoardCard";

export default async function BoardsPage() {
  let boards: Awaited<ReturnType<typeof fetchBoards>> = [];
  let errorMessage: string | null = null;

  try {
    boards = await fetchBoards();
  } catch (err) {
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading your boards.";
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Boards</h1>
        <p className="mt-1 text-ink-muted text-sm">
          Your own curated groupings of posts — separate from Instagram&apos;s saved collections. Each board can
          hold sub-collections for a second level of organization.
        </p>
      </div>

      <div className="mb-8 max-w-md">
        <CreateBoardForm />
      </div>

      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {!errorMessage && boards.length === 0 && (
        <p className="text-sm text-ink-muted">No boards yet — create your first one above.</p>
      )}

      {!errorMessage && boards.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {boards.map((board) => (
            <BoardCard key={board.id} board={board} />
          ))}
        </div>
      )}
    </div>
  );
}
