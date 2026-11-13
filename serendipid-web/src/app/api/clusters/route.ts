import { NextRequest, NextResponse } from "next/server";
import { SerendipidApiError } from "@/lib/apiClient";
import { getThemes } from "@/lib/cache";

// Home renders themes by calling getThemes() directly in-process (it's a
// Server Component, no need to round-trip through its own API). This route
// exists for curl-based verification during development and as a stable
// entrypoint for any future consumer (e.g. the mobile app).
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const refresh = searchParams.get("refresh") === "true";

  try {
    const { themes, unclusteredShortcodes } = await getThemes(refresh);
    return NextResponse.json({
      themes,
      unclusteredCount: unclusteredShortcodes.length,
      computedAt: new Date().toISOString(),
    });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
