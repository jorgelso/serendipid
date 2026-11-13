import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { filterPosts, toDisplayPost } from "@/lib/posts";

const DEFAULT_LIMIT = 24;
const MAX_LIMIT = 60;

// Powers Home's "recent" feed and Browse's filtered feed, both with
// client-side "Load more" pagination — the initial page (and every
// subsequent page) only ever fetches as many full post records (thumbnails
// included) as will actually be shown, so payload size never scales with
// total library size.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const offset = Math.max(0, Number(searchParams.get("offset") ?? 0) || 0);
  const limit = Math.min(MAX_LIMIT, Math.max(1, Number(searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT));
  const categoryParam = searchParams.get("category");
  const category = categoryParam ? categoryParam.split(",").filter(Boolean) : undefined;
  const categoryMatch = searchParams.get("categoryMode") === "any" ? "any" : "exact";
  const language = searchParams.get("language") || undefined;
  const collectionId = searchParams.get("collection") || undefined;
  const sortParam = searchParams.get("sort");
  const sort =
    sortParam === "importance" || sortParam === "date_saved" || sortParam === "post_date" ? sortParam : "recent";
  const dir = searchParams.get("dir") === "asc" ? "asc" : "desc";
  const importance = (searchParams.get("importance") || "")
    .split(",")
    .map((v) => Number(v))
    .filter((v) => Number.isInteger(v) && v >= 1 && v <= 5);
  const eloquent = searchParams.get("eloquent") === "true";
  const tutorialParam = searchParams.get("tutorial");
  const tutorial = tutorialParam === "yes" || tutorialParam === "no" ? tutorialParam : undefined;
  const reviewedParam = searchParams.get("reviewed");
  const reviewed = reviewedParam === "yes" || reviewedParam === "no" ? reviewedParam : undefined;

  try {
    const { posts, collections } = await getExport();

    const filtered = filterPosts(posts, collections, {
      category,
      categoryMatch,
      language,
      collectionId,
      sort,
      dir,
      importance,
      eloquent,
      tutorial,
      reviewed,
    });
    const total = filtered.length;
    const page = filtered.slice(offset, offset + limit).map((p) => toDisplayPost(p));

    return NextResponse.json({ posts: page, total, offset, limit });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
