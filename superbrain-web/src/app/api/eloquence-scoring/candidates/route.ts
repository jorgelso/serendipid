import { NextRequest, NextResponse } from "next/server";
import { fetchEloquenceCandidates, SuperBrainApiError } from "@/lib/apiClient";

// Preview for the admin panel's eloquence-scoring card: how many posts
// currently pass scripts/score_eloquence.py's criteria, before spending any
// LLM calls. `force=true` counts already-scored posts too (re-scoring).
export async function GET(request: NextRequest) {
  const force = request.nextUrl.searchParams.get("force") === "true";
  try {
    return NextResponse.json(await fetchEloquenceCandidates(force));
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
