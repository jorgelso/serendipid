import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { resolveThumbnailUrl } from "@/lib/posts";

// Post.thumbnail can be a data: URI with the image inlined as base64 (some
// backends store it that way rather than a /static/... path) — see
// resolveThumbnailUrl's doc comment. Embedding that string directly in a
// page's props (as the /space view briefly did for every one of its points)
// balloons the payload to tens of MB; this route is the fix, giving every
// point a short, cacheable URL instead. /space's points carry
// `/api/thumbnail/{shortcode}` and the actual bytes are only resolved here,
// on request, per-image.
const DATA_URI_RE = /^data:([^;]+);base64,(.+)$/;

// The mime type comes from a stored thumbnail field populated by analyzing
// external Instagram content — not something to trust verbatim as a
// same-origin Content-Type. Restricted to actual image types, with nosniff
// so a browser can't be coaxed into reinterpreting the bytes as anything else.
const ALLOWED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/avif",
]);

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ shortcode: string }> }
) {
  const { shortcode } = await params;

  try {
    const { posts } = await getExport();
    const post = posts.find((p) => p.shortcode === shortcode);
    const thumbnail = post?.thumbnail;
    if (!thumbnail) {
      return NextResponse.json({ error: "No thumbnail for this post." }, { status: 404 });
    }

    const dataMatch = thumbnail.match(DATA_URI_RE);
    if (dataMatch) {
      const [, rawMimeType, base64] = dataMatch;
      const mimeType = rawMimeType.toLowerCase();
      if (!ALLOWED_IMAGE_TYPES.has(mimeType)) {
        return NextResponse.json({ error: "Unsupported thumbnail type." }, { status: 415 });
      }
      const bytes = Buffer.from(base64, "base64");
      return new NextResponse(bytes, {
        headers: {
          "Content-Type": mimeType,
          "Content-Disposition": 'inline; filename="thumbnail"',
          "X-Content-Type-Options": "nosniff",
          "Content-Security-Policy": "default-src 'none'; sandbox",
          // Thumbnails are stamped per-analysis, not mutated in place —
          // safe to cache aggressively.
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
    }

    const resolved = resolveThumbnailUrl(thumbnail);
    if (!resolved) {
      return NextResponse.json({ error: "No thumbnail for this post." }, { status: 404 });
    }
    return NextResponse.redirect(new URL(resolved, request.url));
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
