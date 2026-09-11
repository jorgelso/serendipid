import { NextRequest, NextResponse } from "next/server";
import { uploadManualMedia, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Analyzes a reel from a media file the user supplied by hand, for posts
// Instagram won't serve the backend. The backend runs the full pipeline
// synchronously behind this, so the request is long-lived by design — see
// MANUAL_UPLOAD_TIMEOUT_MS in lib/apiClient.ts.
// The whole analysis runs inside this request on the backend, so the handler
// is long-lived on purpose. Only deployment platforms enforce this; on a
// self-hosted `next start` it's just build-output metadata. The upload size
// ceiling is the backend's own MAX_UPLOAD_BYTES (core/manual_media.py).
export const maxDuration = 900;

export async function POST(request: NextRequest) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid upload." }, { status: 400 });
  }

  const url = form.get("url");
  const file = form.get("file");
  const caption = form.get("caption");
  const username = form.get("username");

  if (typeof url !== "string" || !url) {
    return NextResponse.json({ error: "A post 'url' is required." }, { status: 400 });
  }
  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json({ error: "A non-empty media file is required." }, { status: 400 });
  }

  try {
    const result = await uploadManualMedia({
      url,
      file,
      filename: file.name,
      caption: typeof caption === "string" ? caption : undefined,
      username: typeof username === "string" ? username : undefined,
    });
    // Only a finished analysis writes a row in `analyses` for the cached
    // /export payload to be stale against — a queued upload, a Batch API
    // submission and a scheduled retry all land later, via their own paths.
    if (result.outcome === "analyzed") invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
