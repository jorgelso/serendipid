import { NextRequest, NextResponse } from "next/server";
import { retryDownload, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// One "try downloading this now" attempt for a stuck reel, from the Stuck
// reels panel. Every outcome except an unreachable backend comes back as a
// 200 with a discriminated `outcome` — the caller needs to distinguish
// "Instagram blocked it" (offer a manual upload) from "backend was busy"
// (nothing to decide, it's queued) from a real failure, and HTTP status
// alone can't carry that: the backend answers a blocked download with 202,
// which is itself a success status.
export const maxDuration = 900;

export async function POST(request: NextRequest) {
  let url: unknown;
  try {
    ({ url } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }
  if (typeof url !== "string" || !url) {
    return NextResponse.json({ error: "A post 'url' is required." }, { status: 400 });
  }

  try {
    const result = await retryDownload(url);
    // Only an actual analysis writes a new row for the cached /export payload
    // to be stale against.
    if (result.outcome === "analyzed") invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
