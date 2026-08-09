"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { ClientPost, Theme, VectorSpaceColorSlot, VectorSpacePoint } from "@/types/domain";
import VectorSpaceLegend from "./VectorSpaceLegend";
import PostModal from "./PostModal";

// react-three-fiber's <Canvas> needs a real WebGL context, so it can't be
// part of the server-rendered HTML — loaded client-only, same reasoning as
// any browser-API-only widget in the App Router.
const VectorSpaceScene = dynamic(() => import("./VectorSpaceScene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-ink-muted text-sm">
      Loading scene…
    </div>
  ),
});

interface VectorSpaceViewProps {
  points: VectorSpacePoint[];
  themes: Theme[];
  unclusteredCount: number;
}

export default function VectorSpaceView({ points, themes, unclusteredCount }: VectorSpaceViewProps) {
  const [activeColorSlot, setActiveColorSlot] = useState<VectorSpaceColorSlot | null>(null);
  const [selectedPost, setSelectedPost] = useState<ClientPost | null>(null);
  const [loadingShortcode, setLoadingShortcode] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function handleSelect(shortcode: string) {
    setLoadingShortcode(shortcode);
    setLoadError(null);
    try {
      const res = await fetch(`/api/posts?shortcodes=${encodeURIComponent(shortcode)}`);
      const data: { posts: ClientPost[] } = await res.json();
      const post = data.posts[0];
      if (post) {
        setSelectedPost(post);
      } else {
        setLoadError("Couldn't load that reel.");
      }
    } catch {
      setLoadError("Couldn't load that reel.");
    } finally {
      setLoadingShortcode(null);
    }
  }

  return (
    <div className="fixed inset-0 z-0">
      <VectorSpaceScene points={points} activeColorSlot={activeColorSlot} onSelect={handleSelect} />

      <div className="pointer-events-none absolute inset-0 flex items-start justify-between px-4 pb-4 pt-20">
        <div className="pointer-events-auto rounded-2xl border border-line bg-surface/90 px-4 py-2.5 text-xs text-ink-muted shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
          <span className="font-display font-bold text-ink">{points.length} reels</span> · drag to
          rotate · scroll to zoom
        </div>
        <VectorSpaceLegend
          themes={themes}
          unclusteredCount={unclusteredCount}
          activeColorSlot={activeColorSlot}
          onSelectSlot={setActiveColorSlot}
        />
      </div>

      {loadingShortcode && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="pointer-events-auto rounded-full bg-ink/80 px-4 py-2 text-sm font-bold text-bg backdrop-blur-sm">
            Loading reel…
          </div>
        </div>
      )}

      {loadError && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <div className="pointer-events-auto rounded-full bg-danger-soft px-4 py-2 text-sm font-bold text-coral-ink">
            {loadError}
          </div>
        </div>
      )}

      {selectedPost && <PostModal post={selectedPost} onClose={() => setSelectedPost(null)} />}
    </div>
  );
}
