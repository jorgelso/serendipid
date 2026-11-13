import { NextRequest, NextResponse } from "next/server";
import { SerendipidApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";
import { getRecommendations } from "@/lib/recommendations";
import type { Post, RecommendationStrategy, RecommendationsResponse } from "@/types/domain";

const DEFAULT_LIMIT = 12;
const MAX_LIMIT = 50;
const STRATEGIES: RecommendationStrategy[] = ["cluster", "vector", "hybrid"];

// Home's recommendations rail, with a visible strategy switcher — see
// src/lib/recommendations.ts for the three scorers. Read-only: no
// invalidateCache() here, this route never mutates post data.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const strategyParam = searchParams.get("strategy") ?? "hybrid";
  if (!STRATEGIES.includes(strategyParam as RecommendationStrategy)) {
    return NextResponse.json({ error: "strategy must be cluster, vector, or hybrid" }, { status: 400 });
  }
  const strategy = strategyParam as RecommendationStrategy;
  const limit = Math.min(MAX_LIMIT, Math.max(1, Number(searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT));

  try {
    const result = await getRecommendations(strategy, limit);
    const { posts } = await getExport();
    const byShortcode = new Map(posts.map((p) => [p.shortcode, p]));

    const hydrated = result.items
      .map((item) => byShortcode.get(item.shortcode))
      .filter((p): p is Post => Boolean(p))
      .map((p) => toDisplayPost(p));

    const response: RecommendationsResponse = {
      success: true,
      strategy,
      coldStart: result.coldStart,
      count: hydrated.length,
      posts: hydrated,
    };
    return NextResponse.json(response);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
