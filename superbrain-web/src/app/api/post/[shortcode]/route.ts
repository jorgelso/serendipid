import { NextRequest, NextResponse } from "next/server";
import { deletePost, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Soft-deletes a post (backend sets is_hidden=1) — see deletePost()'s doc
// comment in apiClient.ts for the undo path.
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ shortcode: string }> }
) {
  const { shortcode } = await params;

  try {
    const result = await deletePost(shortcode);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
