"use client";

import { useState } from "react";

interface EloquenceReviewButtonsProps {
  shortcode: string;
  onApproved: () => void;
  onRejected: () => void;
}

type Pending = "idle" | "confirm-reject" | "approving" | "rejecting";

// Per-card human review on /eloquent, rendered by PostCard when
// EloquentFeed asks for it. Approve stamps eloquence_reviewed=1 (backend
// POST /eloquence/approve) and the card hides these buttons; Reject is the
// same "mark as not eloquent" override the bulk Select toolbar uses (POST
// /eloquence-override) and the card removes itself. Reject asks for a
// second click instead of a dialog — an override can't be undone from the
// UI (only reviewed on /eloquent/overrides), but a modal per card would
// make reviewing a few hundred reels miserable.
export default function EloquenceReviewButtons({ shortcode, onApproved, onRejected }: EloquenceReviewButtonsProps) {
  const [pending, setPending] = useState<Pending>("idle");
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, fallback: string) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shortcodes: [shortcode] }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? fallback);
    return data;
  }

  async function approve() {
    setPending("approving");
    setError(null);
    try {
      const data = await post("/api/eloquence-approve", "Couldn't approve this post.");
      if (data.not_found?.length) throw new Error("This post no longer exists.");
      if (data.not_eloquent?.length) throw new Error("This post is no longer marked eloquent.");
      onApproved();
    } catch (err) {
      setPending("idle");
      setError(err instanceof Error ? err.message : "Couldn't approve this post.");
    }
  }

  async function reject() {
    setPending("rejecting");
    setError(null);
    try {
      await post("/api/eloquence-override", "Couldn't reject this post.");
      onRejected();
    } catch (err) {
      setPending("idle");
      setError(err instanceof Error ? err.message : "Couldn't reject this post.");
    }
  }

  const busy = pending === "approving" || pending === "rejecting";

  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={approve}
          disabled={busy}
          className="flex-1 rounded-full bg-teal/15 px-3 py-1.5 text-xs font-bold text-teal-ink hover:bg-teal/25 transition-colors disabled:opacity-50 cursor-pointer"
        >
          {pending === "approving" ? "Approving…" : "✓ Approve"}
        </button>
        {pending === "confirm-reject" ? (
          <>
            <button
              type="button"
              onClick={reject}
              className="flex-1 rounded-full bg-danger px-3 py-1.5 text-xs font-bold text-bg hover:opacity-85 transition-opacity cursor-pointer"
            >
              Confirm reject
            </button>
            <button
              type="button"
              onClick={() => setPending("idle")}
              aria-label="Cancel reject"
              className="rounded-full border border-line px-2.5 py-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors cursor-pointer"
            >
              ✕
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setPending("confirm-reject")}
            disabled={busy}
            className="flex-1 rounded-full bg-danger-soft px-3 py-1.5 text-xs font-bold text-coral-ink hover:bg-danger/20 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {pending === "rejecting" ? "Rejecting…" : "✕ Reject"}
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
