"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ConfirmDialog from "./ConfirmDialog";

interface DeletePostButtonProps {
  shortcode: string;
  title: string | null;
  // Compact icon-only style for tight card layouts (PostCard); a labeled
  // button in more spacious ones (PostDetail).
  variant?: "icon" | "button";
}

type State = "idle" | "confirming" | "deleting" | "done" | "error";

export default function DeletePostButton({ shortcode, title, variant = "icon" }: DeletePostButtonProps) {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleConfirm() {
    setState("deleting");
    try {
      const res = await fetch(`/api/post/${shortcode}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete this post.");
      setState("done");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't delete this post.");
    }
  }

  if (state === "done") {
    return (
      <div className="rounded-xl bg-danger-soft px-3 py-2 text-xs font-bold text-coral-ink flex items-center justify-between gap-2">
        <span>Deleted.</span>
        <button onClick={() => router.refresh()} className="underline shrink-0">
          Refresh
        </button>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setState("confirming")}
        aria-label="Delete post"
        title="Delete"
        className={
          variant === "icon"
            ? "shrink-0 rounded-full w-7 h-7 flex items-center justify-center text-ink-muted hover:bg-danger-soft hover:text-coral-ink transition-colors"
            : "shrink-0 text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
        }
      >
        {variant === "icon" ? "🗑" : "🗑 Delete"}
      </button>

      {(state === "confirming" || state === "deleting" || state === "error") && (
        <ConfirmDialog
          title="Delete this reel?"
          message={
            (title ? `"${title}" ` : "This reel ") +
            "will be hidden from your library. You can undo this later by re-sharing the same URL — it restores instead of re-downloading." +
            (state === "error" && message ? `\n\n${message}` : "")
          }
          confirmLabel={state === "deleting" ? "Deleting…" : "Delete"}
          danger
          busy={state === "deleting"}
          onConfirm={handleConfirm}
          onCancel={() => setState("idle")}
        />
      )}
    </>
  );
}
