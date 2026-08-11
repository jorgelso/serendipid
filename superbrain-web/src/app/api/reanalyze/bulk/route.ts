import { NextRequest, NextResponse } from "next/server";
import { bulkReanalyze, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Kicks off a bulk rescan for many shortcodes at once (a whole version
// cohort, or a single shortcode when used as the per-card action on the
// "cheap fix" version-7 panel — see PostCard's rescanMode prop). Returns
// almost immediately; queued items finish asynchronously via the backend's
// background worker — see useBulkRescanProgress for how the UI tracks that.
export async function POST(request: NextRequest) {
  let shortcodes: unknown;
  try {
    ({ shortcodes } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (!Array.isArray(shortcodes) || shortcodes.length === 0 || !shortcodes.every((s) => typeof s === "string")) {
    return NextResponse.json({ error: "A non-empty 'shortcodes' array of strings is required." }, { status: 400 });
  }

  try {
    const result = await bulkReanalyze(shortcodes);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
