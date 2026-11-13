import { NextRequest, NextResponse } from "next/server";
import { fetchSemanticSearch, SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { mergeSearchHitsWithPosts } from "@/lib/posts";

function clamp(n: number, min: number, max: number): number {
  if (Number.isNaN(n)) return min;
  return Math.min(max, Math.max(min, n));
}

function errorResponse(err: unknown) {
  if (err instanceof SuperBrainApiError) {
    return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
  }
  return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q")?.trim();
  if (!q) {
    return NextResponse.json({ error: "Query parameter 'q' is required." }, { status: 400 });
  }
  const limit = clamp(Number(searchParams.get("limit") ?? 20), 1, 100);
  const minSimilarity = clamp(Number(searchParams.get("min_similarity") ?? 0), 0, 1);

  try {
    const [searchResponse, exportPayload] = await Promise.all([
      fetchSemanticSearch(q, limit, minSimilarity),
      getExport(),
    ]);
    const results = mergeSearchHitsWithPosts(searchResponse.data, exportPayload.posts);
    return NextResponse.json({ query: q, count: results.length, results });
  } catch (err) {
    return errorResponse(err);
  }
}
