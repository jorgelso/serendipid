"use client";

import { useState } from "react";
import type { ClientPost } from "@/types/domain";
import { classifyMedia, isMissingVideo } from "@/lib/media";
import ReanalyzeButton from "./ReanalyzeButton";

function Carousel({
  items,
  kind,
  onVideoTimeUpdate,
}: {
  items: string[];
  kind: "video" | "image";
  onVideoTimeUpdate?: (currentTime: number, duration: number) => void;
}) {
  const [index, setIndex] = useState(0);
  const src = items[Math.min(index, items.length - 1)];

  return (
    <div>
      <div className="rounded-2xl overflow-hidden bg-ink flex items-center justify-center">
        {kind === "video" ? (
          <video
            key={src}
            src={src}
            controls
            className="w-full max-h-[70vh]"
            onTimeUpdate={(e) =>
              onVideoTimeUpdate?.(e.currentTarget.currentTime, e.currentTarget.duration)
            }
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt="" className="w-full max-h-[70vh] object-contain" />
        )}
      </div>
      {items.length > 1 && (
        <div className="mt-2 flex items-center justify-center gap-3">
          <button
            onClick={() => setIndex((i) => (i - 1 + items.length) % items.length)}
            className="rounded-full border border-line px-3 py-1 text-sm font-bold hover:bg-surface-2"
            aria-label="Previous"
          >
            ‹
          </button>
          <span className="text-xs font-bold text-ink-muted">
            {index + 1} / {items.length}
          </span>
          <button
            onClick={() => setIndex((i) => (i + 1) % items.length)}
            className="rounded-full border border-line px-3 py-1 text-sm font-bold hover:bg-surface-2"
            aria-label="Next"
          >
            ›
          </button>
        </div>
      )}
    </div>
  );
}

export default function MediaViewer({
  post,
  onVideoTimeUpdate,
}: {
  post: ClientPost;
  onVideoTimeUpdate?: (currentTime: number, duration: number) => void;
}) {
  const { videos, images } = classifyMedia(post.media_urls);

  if (videos.length > 0) {
    return <Carousel items={videos} kind="video" onVideoTimeUpdate={onVideoTimeUpdate} />;
  }

  if (images.length > 0) {
    return <Carousel items={images} kind="image" />;
  }

  if (isMissingVideo(post)) {
    return (
      <div className="rounded-2xl bg-yellow-soft p-6 text-center">
        <p className="font-display font-semibold text-yellow-ink mb-1">Video not downloaded</p>
        <p className="text-sm text-yellow-ink/80 mb-4">
          This post was saved before local video storage — re-fetching it will download and store
          the original.
        </p>
        <div className="flex justify-center">
          <ReanalyzeButton url={post.url} label="Re-fetch video" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-surface-2 p-6 text-center">
      <p className="text-sm text-ink-muted mb-3">
        No local copy is stored for this kind of post.
      </p>
      <a
        href={post.url}
        target="_blank"
        rel="noreferrer"
        className="text-sm font-bold text-coral-ink underline"
      >
        Open the original
      </a>
    </div>
  );
}
