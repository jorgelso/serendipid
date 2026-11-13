import { NextRequest, NextResponse } from "next/server";
import { SerendipidApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { filterVersionPosts, toDisplayPost } from "@/lib/posts";

const DEFAULT_LIMIT = 24;
const MAX_LIMIT = 60;

// Same "load more" pagination pattern as /api/feed, scoped to one
// analysis_version instead of the whole library — powers each panel in
// VersionPanel's auto-load-on-scroll grid.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const version = Number(searchParams.get("version"));
  const offset = Math.max(0, Number(searchParams.get("offset") ?? 0) || 0);
  const limit = Math.min(MAX_LIMIT, Math.max(1, Number(searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT));
  const category = searchParams.get("category") || undefined;
  const language = searchParams.get("language") || undefined;
  const sortParam = searchParams.get("sort");
  const sort =
    sortParam === "importance" || sortParam === "date_saved" || sortParam === "post_date" ? sortParam : "recent";

  if (!Number.isFinite(version)) {
    return NextResponse.json({ error: "A numeric 'version' is required." }, { status: 400 });
  }

  try {
    const { posts } = await getExport();

    const filtered = filterVersionPosts(posts, version, { category, language, sort });
    const total = filtered.length;
    const page = filtered.slice(offset, offset + limit).map((p) => toDisplayPost(p));

    return NextResponse.json({ posts: page, total, offset, limit, version });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
