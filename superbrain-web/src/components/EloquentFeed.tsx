"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ClientPost } from "@/types/domain";
import InfiniteFeed from "./InfiniteFeed";
import ConfirmDialog from "./ConfirmDialog";

interface EloquentFeedProps {
  feedKey: string;
  initialPosts: ClientPost[];
  total: number;
  pageSize: number;
  params: Record<string, string>;
  // Whether the active filter hides approved posts (reviewed=no) — decides
  // whether an Approve click also shrinks the server-side list.
  hidesApproved: boolean;
}

type ConfirmState = "idle" | "confirming" | "submitting" | "error";

// Wraps InfiniteFeed with a "Select" toggle + bulk "mark as not eloquent"
// toolbar — the human-correction path for scripts/score_eloquence.py false
// positives (POST /api/eloquence-override -> backend POST /eloquence/override).
// Selection state lives here rather than in InfiniteFeed so it survives
// "Load more" adding fresh posts to that component's own internal state.
export default function EloquentFeed({
  feedKey,
  initialPosts,
  total,
  pageSize,
  params,
  hidesApproved,
}: EloquentFeedProps) {
  const router = useRouter();
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmState, setConfirmState] = useState<ConfirmState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  // Per-card review (EloquenceReviewButtons via PostCard): cards handle
  // their own hide/collapse; this only tracks how many have left the
  // server-side list so InfiniteFeed's next "Load more" offset stays right.
  const [removedCount, setRemovedCount] = useState(0);
  const eloquenceReview = {
    onApproved: () => {
      if (hidesApproved) setRemovedCount((n) => n + 1);
    },
    onRejected: () => setRemovedCount((n) => n + 1),
  };

  function toggleSelect(shortcode: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(shortcode)) next.delete(shortcode);
      else next.add(shortcode);
      return next;
    });
  }

  function stopSelecting() {
    setSelecting(false);
    setSelected(new Set());
    setConfirmState("idle");
    setMessage(null);
  }

  async function handleConfirm() {
    setConfirmState("submitting");
    try {
      const res = await fetch("/api/eloquence-override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcodes: Array.from(selected) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't update these posts.");
      stopSelecting();
      router.refresh();
    } catch (err) {
      setConfirmState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't update these posts.");
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
          className="rounded-full border border-line text-ink text-sm font-bold px-4 py-1.5 hover:bg-surface-2 transition-colors cursor-pointer"
        >
          {selecting ? "Cancel" : "Select"}
        </button>

        {selecting && (
          <button
            type="button"
            onClick={() => setConfirmState("confirming")}
            disabled={selected.size === 0}
            className="rounded-full bg-danger text-bg text-sm font-bold px-4 py-1.5 hover:opacity-85 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Mark {selected.size > 0 ? selected.size : ""} as not eloquent
          </button>
        )}
      </div>

      <InfiniteFeed
        key={feedKey}
        initialPosts={initialPosts}
        total={total}
        pageSize={pageSize}
        params={params}
        selectable={selecting}
        selectedShortcodes={selected}
        onToggleSelect={toggleSelect}
        eloquenceReview={eloquenceReview}
        removedCount={removedCount}
      />

      {(confirmState === "confirming" || confirmState === "submitting" || confirmState === "error") && (
        <ConfirmDialog
          title="Mark as not eloquent?"
          message={
            `${selected.size} post${selected.size === 1 ? "" : "s"} will be removed from the Eloquent list.` +
            (confirmState === "error" && message ? `\n\n${message}` : "")
          }
          confirmLabel={confirmState === "submitting" ? "Marking…" : "Mark as not eloquent"}
          danger
          busy={confirmState === "submitting"}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmState("idle")}
        />
      )}
    </div>
  );
}
