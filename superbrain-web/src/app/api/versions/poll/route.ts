import { NextRequest, NextResponse } from "next/server";
import { fetchQueueStatus, SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
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
    // that hit a quota/rate-limit failure gets parked there by main.py for
    // ~24h before automatically retrying, which this endpoint treats the
    // same as "not currently tracked" rather than "still pending". Its row
    // was already hard-deleted when the bulk rescan started (see
    // POST /reanalyze/bulk), so it won't appear in `finished` either until
    // the retry actually succeeds — it just quietly drops out of the
    // client's polling loop in the meantime, same as any other post that
    // never got saved. A future improvement could surface retry_queue
    // membership explicitly instead.
    const queueStatus = await fetchQueueStatus();
    const stillPending = new Set([
      ...queueStatus.currently_processing,
      ...queueStatus.queue.map((q) => q.shortcode),
    ]);

    const finishedShortcodes = shortcodes.filter((sc) => !stillPending.has(sc));
    const stillPendingShortcodes = shortcodes.filter((sc) => stillPending.has(sc));

    if (finishedShortcodes.length === 0) {
      return NextResponse.json({ finished: [], stillPendingShortcodes });
    }

    invalidateCache();
    const config = getConfig();
    const { posts } = await getExport();
    const finishedSet = new Set(finishedShortcodes);
    const finished = posts
      .filter((p) => finishedSet.has(p.shortcode))
      .map((p) => toDisplayPost(p, config.apiUrl));

    return NextResponse.json({ finished, stillPendingShortcodes });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
