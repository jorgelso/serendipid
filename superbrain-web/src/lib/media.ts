// Classifies a post's stored media (backend/core/media_store.py) into what's
// actually playable/viewable. Carousels use numbered filenames ("1.mp4",
// "2.jpg", "10.jpg", ...) which the backend returns in lexicographic order —
// "10.jpg" sorts before "2.jpg" as plain strings — so everything here sorts
// by the leading number instead.

const VIDEO_EXTENSIONS = [".mp4", ".mov", ".webm"];
const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif"];

function leadingNumber(url: string): number {
  const filename = url.split("/").pop() ?? url;
  const match = filename.match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}

function hasExtension(url: string, extensions: string[]): boolean {
  const lower = url.toLowerCase();
  return extensions.some((ext) => lower.endsWith(ext));
}

function naturalSort(urls: string[]): string[] {
  return [...urls].sort((a, b) => leadingNumber(a) - leadingNumber(b));
}

export interface ClassifiedMedia {
  videos: string[];
  images: string[];
}

/** mediaUrls should already be resolved to absolute URLs (see
 * resolveMediaUrls) — audio/info.txt entries are deliberately excluded, they
 * aren't something to show in a viewer. */
export function classifyMedia(mediaUrls: string[]): ClassifiedMedia {
  return {
    videos: naturalSort(mediaUrls.filter((u) => hasExtension(u, VIDEO_EXTENSIONS))),
    images: naturalSort(mediaUrls.filter((u) => hasExtension(u, IMAGE_EXTENSIONS))),
  };
}

/** The specific "missing, needs re-fetch" condition — deliberately NOT tied
 * to needs_review (a separate, unrelated signal) and deliberately excludes
 * non-Instagram content types, which never have local media by design. */
export function isMissingVideo(post: { content_type: string; media_urls: string[] }): boolean {
  if (post.content_type !== "instagram") return false;
  return !post.media_urls.some((u) => hasExtension(u, VIDEO_EXTENSIONS));
}
