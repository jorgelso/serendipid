"use client";

import { useCallback, useEffect, useRef } from "react";
import type { ClientPost } from "@/types/domain";
import { classifyMedia } from "./media";

// Video posts qualify at >=60% watched; non-video posts (image/carousel, no
// inherent playback duration) qualify after staying open >=20s. Fires once
// per mount (a post reopened later logs a fresh event — repeat views are a
// deliberate signal for the Home recommendation engine, not deduped).
const NON_VIDEO_DWELL_MS = 20_000;
const VIDEO_WATCH_FRACTION = 0.6;

function logView(shortcode: string) {
  fetch(`/api/post/${shortcode}/view`, { method: "POST" }).catch(() => {});
}

export function useQualifyingView(post: ClientPost): {
  onVideoTimeUpdate: (currentTime: number, duration: number) => void;
} {
  const firedRef = useRef(false);
  const { videos } = classifyMedia(post.media_urls);
  const hasVideo = videos.length > 0;

  useEffect(() => {
    firedRef.current = false;
    if (hasVideo) return; // qualifies via onVideoTimeUpdate instead

    const timer = setTimeout(() => {
      if (!firedRef.current) {
        firedRef.current = true;
        logView(post.shortcode);
      }
    }, NON_VIDEO_DWELL_MS);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hasVideo is derived from post.media_urls, already covered by post.shortcode identity in practice
  }, [post.shortcode]);

  const onVideoTimeUpdate = useCallback(
    (currentTime: number, duration: number) => {
      if (firedRef.current || !duration) return;
      // First video in a carousel to reach the threshold qualifies the whole post.
      if (currentTime / duration >= VIDEO_WATCH_FRACTION) {
        firedRef.current = true;
        logView(post.shortcode);
      }
    },
    [post.shortcode]
  );

  return { onVideoTimeUpdate };
}
