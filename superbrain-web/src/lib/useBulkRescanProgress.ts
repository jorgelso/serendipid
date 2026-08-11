"use client";

import { useEffect, useState } from "react";
import type { ClientPost } from "@/types/domain";

interface PollResponse {
  finished: ClientPost[];
  stillPendingShortcodes: string[];
}

// Polls /api/versions/poll every ~8s (a bit past the backend's 5s queue-
// worker tick) for a set of shortcodes queued by a bulk rescan, until none
// remain pending. `finishedPosts` accumulates across polls — callers should
// consume and clear what they need rather than expecting it to reset itself.
export function useBulkRescanProgress(queuedShortcodes: string[]) {
  const key = queuedShortcodes.join(",");

  // Reset `pending` whenever the caller hands us a new batch (e.g. a fresh
  // bulk-rescan kickoff) — done during render, not in an effect, per
  // React's guidance for "adjusting state when a prop changes"
  // (https://react.dev/learn/you-might-not-need-an-effect): calling
  // setState synchronously inside an effect body triggers a needless extra
  // render pass, which this sidesteps entirely.
  const [trackedKey, setTrackedKey] = useState(key);
  const [pending, setPending] = useState<string[]>(queuedShortcodes);
  if (key !== trackedKey) {
    setTrackedKey(key);
    setPending(queuedShortcodes);
  }

  const [finishedPosts, setFinishedPosts] = useState<ClientPost[]>([]);

  useEffect(() => {
    if (pending.length === 0) return;

    const id = setInterval(async () => {
      try {
        const res = await fetch(`/api/versions/poll?shortcodes=${pending.join(",")}`);
        if (!res.ok) return;
        const data = (await res.json()) as PollResponse;
        if (data.finished?.length) {
          setFinishedPosts((prev) => [...prev, ...data.finished]);
        }
        setPending(data.stillPendingShortcodes ?? []);
      } catch {
        // Transient network error — leave `pending` as-is, try again next tick.
      }
    }, 8000);

    return () => clearInterval(id);
  }, [pending]);

  return { pending, finishedPosts };
}
