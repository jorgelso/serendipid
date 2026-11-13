import { NextRequest, NextResponse } from "next/server";
import { reanalyzePost, SerendipidApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Kicks off a forced re-analysis of a post whose category taxonomy is out of
// date (needs_review). This runs the full pipeline synchronously on the
// backend (can take minutes) — see REANALYZE_TIMEOUT_MS in lib/apiClient.ts.
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
    const result = await reanalyzePost(url);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
