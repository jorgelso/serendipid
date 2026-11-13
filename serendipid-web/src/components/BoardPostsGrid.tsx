"use client";

import Link from "next/link";
import type { LightPost } from "./PostPicker";

interface BoardPostsGridProps {
  shortcodes: string[];
  postsByShortcode: Map<string, LightPost>;
  onRemove: (shortcode: string) => Promise<void>;
  removingShortcode: string | null;
  // When set, clicking a thumbnail toggles it in/out of `selected` instead of
  // navigating to the post — used by BoardDetail's "Select for sub-board"
  // mode so picking reels for a new/existing sub-board doesn't require
  // searching a title out of a large board via PostPicker.
  selectable?: boolean;
  selected?: Set<string>;
  onToggleSelect?: (shortcode: string) => void;
  // Shortcodes with at least one qualifying view (backend's post_views table,
  // via GET /view-history) — renders a translucent white overlay so an
  // already-watched reel visually recedes without leaving the board. A
  // should_revisit flag (below) always wins over this: a post the user has
  // watched but wants to come back to shouldn't read as "done."
  seenShortcodes?: Set<string>;
  onToggleRevisit?: (shortcode: string, next: boolean) => void;
  revisitingShortcode?: string | null;
}

// Thumbnails come from /api/thumbnail/[shortcode] (existing proxy — see its
// doc comment) rather than embedding thumbnail bytes in the page payload.
export default function BoardPostsGrid({
  shortcodes,
  postsByShortcode,
  onRemove,
  removingShortcode,
  selectable = false,
  selected,
  onToggleSelect,
  seenShortcodes,
  onToggleRevisit,
  revisitingShortcode,
}: BoardPostsGridProps) {
  if (shortcodes.length === 0) {
    return <p className="text-xs text-ink-muted">No posts yet.</p>;
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
      {shortcodes.map((shortcode) => {
        const post = postsByShortcode.get(shortcode);
        const isSelected = selectable && !!selected?.has(shortcode);
        const shouldRevisit = !!post?.should_revisit;
        const isSeen = !!seenShortcodes?.has(shortcode);
        const thumb = (
          <>
            <div className="relative">
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
              {shouldRevisit ? (
                <div className="absolute inset-0 flex items-end justify-center bg-rose/40 pb-1.5 pointer-events-none">
                  <span className="rounded-full bg-rose text-white text-[10px] font-bold px-2 py-0.5 shadow-sm">
                    Should revisit
                  </span>
                </div>
              ) : (
                isSeen && <div className="absolute inset-0 bg-white/50 pointer-events-none" />
              )}
            </div>
            <p className="px-2 py-1.5 text-[11px] leading-snug line-clamp-2">
              {post?.title || "Untitled reel"}
            </p>
          </>
        );
        return (
          <div
            key={shortcode}
            className={`relative rounded-2xl overflow-hidden border bg-surface-2 ${
              isSelected ? "border-coral-ink ring-2 ring-coral-ink" : "border-line"
            }`}
          >
            {selectable ? (
              <button type="button" onClick={() => onToggleSelect?.(shortcode)} className="block w-full text-left">
                {thumb}
              </button>
            ) : (
              <Link href={`/post/${shortcode}`} className="block">
                {thumb}
              </Link>
            )}
            {selectable ? (
              <span
                aria-hidden
                className={`absolute top-1.5 left-1.5 w-5 h-5 rounded-full border-2 flex items-center justify-center text-[10px] font-bold pointer-events-none ${
                  isSelected ? "bg-coral-ink border-coral-ink text-bg" : "bg-surface/80 border-line text-transparent"
                }`}
              >
                ✓
              </span>
            ) : (
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
            )}
            {onToggleRevisit && (
              <button
                type="button"
                disabled={revisitingShortcode === shortcode}
                onClick={() => onToggleRevisit(shortcode, !shouldRevisit)}
                aria-label={shouldRevisit ? "Unmark as should revisit" : "Mark as should revisit"}
                title={shouldRevisit ? "Unmark as should revisit" : "Mark as should revisit"}
                className={`absolute bottom-1.5 right-1.5 w-6 h-6 rounded-full text-sm flex items-center justify-center transition-colors disabled:opacity-50 ${
                  shouldRevisit ? "bg-rose text-white" : "bg-ink/70 text-bg hover:bg-rose"
                }`}
              >
                🔖
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
