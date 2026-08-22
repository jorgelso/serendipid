"use client";

import Link from "next/link";
import type { LightPost } from "./PostPicker";

interface BoardPostsGridProps {
  shortcodes: string[];
  postsByShortcode: Map<string, LightPost>;
  onRemove: (shortcode: string) => Promise<void>;
  removingShortcode: string | null;
}

// Thumbnails come from /api/thumbnail/[shortcode] (existing proxy — see its
// doc comment) rather than embedding thumbnail bytes in the page payload.
export default function BoardPostsGrid({
  shortcodes,
  postsByShortcode,
  onRemove,
  removingShortcode,
}: BoardPostsGridProps) {
  if (shortcodes.length === 0) {
    return <p className="text-xs text-ink-muted">No posts yet.</p>;
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
      {shortcodes.map((shortcode) => {
        const post = postsByShortcode.get(shortcode);
        return (
          <div key={shortcode} className="relative rounded-2xl overflow-hidden border border-line bg-surface-2">
            <Link href={`/post/${shortcode}`} className="block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/thumbnail/${shortcode}`}
                alt=""
                className="w-full aspect-square object-cover bg-surface-2"
                loading="lazy"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
              <p className="px-2 py-1.5 text-[11px] leading-snug line-clamp-2">
                {post?.title || "Untitled reel"}
              </p>
            </Link>
            <button
              type="button"
              disabled={removingShortcode === shortcode}
              onClick={() => onRemove(shortcode)}
              aria-label="Remove from board"
              title="Remove"
              className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-ink/70 text-bg text-sm flex items-center justify-center hover:bg-danger transition-colors disabled:opacity-50"
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
