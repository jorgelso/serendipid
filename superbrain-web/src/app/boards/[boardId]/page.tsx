import { notFound } from "next/navigation";
import { fetchBoard, SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import BoardDetail from "@/components/BoardDetail";

export default async function BoardDetailPage(props: PageProps<"/boards/[boardId]">) {
  const { boardId } = await props.params;

  let errorMessage: string | null = null;
  let board: Awaited<ReturnType<typeof fetchBoard>> | null = null;
  let lightPosts: { shortcode: string; title: string | null; username: string }[] = [];

  try {
    const [{ posts }, fetchedBoard] = await Promise.all([getExport(), fetchBoard(boardId)]);
    board = fetchedBoard;
    // Only title/username/shortcode — enough for the "add posts" picker's
    // text search, without shipping every post's summary/transcripts/thumbnail
    // to the client (see /api/thumbnail/[shortcode] for how thumbnails are
    // fetched cheaply on demand instead).
    lightPosts = posts.map((p) => ({ shortcode: p.shortcode, title: p.title, username: p.username }));
  } catch (err) {
    if (err instanceof SuperBrainApiError && err.status === 404) {
      notFound();
    }
    errorMessage = err instanceof SuperBrainApiError ? err.message : "Something went wrong loading this board.";
  }

  if (!errorMessage && !board) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-8">
      {errorMessage && (
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      )}

      {board && <BoardDetail board={board} allPosts={lightPosts} />}
    </div>
  );
}
