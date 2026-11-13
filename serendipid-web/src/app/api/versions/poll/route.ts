import { NextRequest, NextResponse } from "next/server";
import { fetchQueueStatus, SerendipidApiError } from "@/lib/apiClient";
import { getExport, invalidateCache } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";

// Backs useBulkRescanProgress. There's no dedicated per-batch job-status
// endpoint on the backend, so this composes the existing GET /queue-status
// (which shortcodes are still processing/queued) with a cache-invalidate +
// re-fetch for whichever of the given shortcodes are no longer pending —
// those have finished (successfully or not) and are returned so the UI can
// drop them from the panel's "still stale" list.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const shortcodes = (searchParams.get("shortcodes") ?? "").split(",").filter(Boolean);

  if (shortcodes.length === 0) {
    return NextResponse.json({ finished: [], stillPendingShortcodes: [] });
  }

  try {
    // NOTE: deliberately not checking queueStatus.retry_queue — a shortcode
    // that hit a quota/rate-limit failure gets parked there for ~24h before
    // automatically retrying, which this endpoint treats the same as "not
    // currently tracked" rather than "still pending". Unlike the old
    // destructive rescan path, the post's row is NEVER deleted by a rescan
    // (see backend/CLAUDE.md's "Rescan pipeline" section) — a rate-limited
    // or failed rescan just leaves the existing row as-is, so it quietly
    // drops out of the client's polling loop with its prior data intact,
    // rather than disappearing. A future improvement could surface
    // retry_queue membership explicitly instead of dropping it silently.
    //
    // rescan_batch_pending covers shortcodes submitted to a shared OpenAI
    // batch job (ANALYSIS_MODE=batch) — they leave currently_processing/queue
    // once submitted, so without this they'd be wrongly read as "finished"
    // the moment local analyzer steps wrap up, well before the batch itself
    // resolves.
    const queueStatus = await fetchQueueStatus();
    const stillPending = new Set([
      ...queueStatus.currently_processing,
      ...queueStatus.queue.map((q) => q.shortcode),
      ...queueStatus.rescan_batch_pending.map((j) => j.shortcode),
    ]);

    const finishedShortcodes = shortcodes.filter((sc) => !stillPending.has(sc));
    const stillPendingShortcodes = shortcodes.filter((sc) => stillPending.has(sc));

    if (finishedShortcodes.length === 0) {
      return NextResponse.json({ finished: [], stillPendingShortcodes });
    }

    invalidateCache();
    const { posts } = await getExport();
    const finishedSet = new Set(finishedShortcodes);
    const finished = posts
      .filter((p) => finishedSet.has(p.shortcode))
      .map((p) => toDisplayPost(p));

    return NextResponse.json({ finished, stillPendingShortcodes });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
