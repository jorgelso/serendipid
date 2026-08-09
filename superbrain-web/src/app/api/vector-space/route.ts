import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getThemes, getVectorSpace } from "@/lib/cache";

// The /space page renders by calling getVectorSpace()/getThemes() directly
// (it's a Server Component, no need to round-trip through its own API,
// same reasoning as /api/clusters). This route exists for curl-based
// verification during development and as a stable entrypoint for any
// future consumer.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const refresh = searchParams.get("refresh") === "true";

  try {
    const points = await getVectorSpace(refresh);
    const { themes } = await getThemes(false);
    return NextResponse.json({
      points,
      themes,
      computedAt: new Date().toISOString(),
    });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
