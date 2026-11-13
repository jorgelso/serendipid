import { NextRequest, NextResponse } from "next/server";
import { logPostView, SerendipidApiError } from "@/lib/apiClient";

// Logs a qualifying view (video >=60% watched, non-video open >=20s — see
// useQualifyingView) for the Home recommendation engine. No invalidateCache()
// — a view never changes post data, only personalization signal history.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ shortcode: string }> }
) {
  const { shortcode } = await params;

  try {
    const result = await logPostView(shortcode);
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
