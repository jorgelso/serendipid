import { NextRequest, NextResponse } from "next/server";
import { fetchSemanticSearch, SuperBrainApiError } from "@/lib/apiClient";

// Backs the /space page's "illuminate" search box: same cosine-similarity
// endpoint as /search, but only the matched shortcodes are needed (the
// scene already has everything else about each point) — the client
// highlights them by treating the match set as a shortcode allowlist, same
// mechanism as clicking a theme in the legend.
const RESULT_LIMIT = 80;
const MIN_SIMILARITY = 0.15;

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q")?.trim() ?? "";

  if (!q) {
    return NextResponse.json({ shortcodes: [] });
  }

  try {
    const result = await fetchSemanticSearch(q, RESULT_LIMIT, MIN_SIMILARITY);
    return NextResponse.json({ shortcodes: result.data.map((hit) => hit.shortcode) });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
