"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import type { ClientPost } from "@/types/domain";
import PostDetail from "./PostDetail";

interface PostModalProps {
  post: ClientPost;
  onClose: () => void;
}

export default function PostModal({ post, onClose }: PostModalProps) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  // Rendered via a portal straight to <body> — PostCard has a hover
  // transform (hover:-translate-y-1/rotate), and any ancestor with an active
  // CSS transform becomes the containing block for `fixed` descendants. Left
  // as a normal child, this modal would size/position itself against the
  // card instead of the viewport whenever that hover transform was active,
  // which is exactly the "sometimes centered, sometimes card-sized, laggy
  // while moving the cursor" bug — the containing block was flipping back
  // and forth as the hover state toggled mid-animation. A portal escapes
  // the card's DOM subtree entirely, so no ancestor transform can ever
  // affect it.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-3xl bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-end">
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 -mt-2 -mr-2 rounded-full w-8 h-8 flex items-center justify-center hover:bg-surface-2 text-lg"
          >
            ×
          </button>
        </div>

        <PostDetail initialPost={post} />

        <div className="mt-5">
          <Link
            href={`/post/${post.shortcode}`}
            className="inline-block rounded-full bg-ink text-bg font-display font-semibold text-sm px-5 py-2.5 hover:opacity-85 transition-opacity"
          >
            Open full page →
          </Link>
        </div>
      </div>
    </div>,
    document.body
  );
}
