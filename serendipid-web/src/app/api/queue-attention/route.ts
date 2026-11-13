import { NextRequest, NextResponse } from "next/server";
import { fetchQueueAttention, SerendipidApiError } from "@/lib/apiClient";

// Reels that are pending or abandoned — powers the "Stuck reels" panel on
// /admin. Deliberately not routed through cache.ts: the backing state changes
// on its own while an import job runs, so a cached copy would be wrong within
// seconds.

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  try {
    const result = await fetchQueueAttention({
      includeAnalyzed: params.get("includeAnalyzed") === "true",
      includeDeleted: params.get("includeDeleted") === "true",
    });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
