import { NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getExport, getThemes, invalidateCache } from "@/lib/cache";

// Invalidates and eagerly re-fetches/recomputes (rather than just clearing)
// so a misconfigured backend (down, wrong key) surfaces immediately in this
// response instead of silently appearing on the next page load.
export async function POST() {
  invalidateCache();
  try {
    const exportPayload = await getExport(true);
    const { themes } = await getThemes(true);
    return NextResponse.json({
      refreshedAt: new Date().toISOString(),
      postCount: exportPayload.posts.length,
      themeCount: themes.length,
    });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
