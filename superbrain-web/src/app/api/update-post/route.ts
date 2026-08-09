import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError, updatePost, type PostEdits } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

export async function POST(request: NextRequest) {
  let body: { shortcode?: unknown } & PostEdits;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const { shortcode, ...edits } = body;
  if (typeof shortcode !== "string" || !shortcode) {
    return NextResponse.json({ error: "A post 'shortcode' is required." }, { status: 400 });
  }

  try {
    const result = await updatePost(shortcode, edits);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
