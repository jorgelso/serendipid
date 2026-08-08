import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getConfig } from "@/lib/config";
import { getExport } from "@/lib/cache";
import { toDisplayPost } from "@/lib/posts";

// Fetches full post records (including base64/large thumbnails) for a
// specific set of shortcodes only. Kept separate from /api/clusters and the
// Home page's initial render, which only ever carry lightweight text (labels,
// counts, shortcodes) — post content loads on demand when a section is
// actually expanded, so the initial page stays small regardless of library size.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const shortcodes = (searchParams.get("shortcodes") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (shortcodes.length === 0) {
    return NextResponse.json({ posts: [] });
  }

  try {
    const config = getConfig();
    const { posts } = await getExport();
    const wanted = new Set(shortcodes);
    const results = posts.filter((p) => wanted.has(p.shortcode)).map((p) => toDisplayPost(p, config.apiUrl));
    return NextResponse.json({ posts: results });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
