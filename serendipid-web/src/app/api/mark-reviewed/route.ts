import { NextRequest, NextResponse } from "next/server";
import { markReviewed, SerendipidApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// "Keep as is" — acknowledges a needs_review post without re-running
// analysis, stamping it with the current analysis_version on the backend.
export async function POST(request: NextRequest) {
  let shortcode: unknown;
  try {
    ({ shortcode } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (typeof shortcode !== "string" || !shortcode) {
    return NextResponse.json({ error: "A post 'shortcode' is required." }, { status: 400 });
  }

  try {
    const result = await markReviewed(shortcode);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
