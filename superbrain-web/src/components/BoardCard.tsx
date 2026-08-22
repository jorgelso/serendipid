"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Board } from "@/types/domain";
import { refreshBoards } from "@/lib/useBoards";
import ConfirmDialog from "./ConfirmDialog";

export default function BoardCard({ board }: { board: Board }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete this board.");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setDeleting(false);
      setConfirming(false);
      setError(err instanceof Error ? err.message : "Couldn't delete this board.");
    }
  }

  const subPostCount = board.subcollections.reduce((sum, s) => sum + s.post_ids.length, 0);

  return (
    <div className="rounded-3xl bg-surface border border-line p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/boards/${board.id}`} className="min-w-0 group">
          <h2 className="font-display font-semibold text-lg leading-snug group-hover:text-coral-ink transition-colors truncate">
            {board.icon ?? "🗂️"} {board.name}
          </h2>
        </Link>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="shrink-0 text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
        >
          🗑 Delete
        </button>
      </div>

      <p className="text-xs text-ink-muted">
        {board.post_ids.length} post{board.post_ids.length === 1 ? "" : "s"}
        {board.subcollections.length > 0 &&
          ` · ${board.subcollections.length} sub-collection${board.subcollections.length === 1 ? "" : "s"} (${subPostCount} post${subPostCount === 1 ? "" : "s"})`}
      </p>

      <Link
        href={`/boards/${board.id}`}
        className="mt-1 inline-block self-start rounded-full border border-line text-xs font-bold px-3.5 py-1.5 hover:bg-surface-2 transition-colors"
      >
        Open board →
      </Link>

      {error && <p className="text-xs text-danger">{error}</p>}

      {confirming && (
        <ConfirmDialog
          title={`Delete "${board.name}"?`}
          message={`This deletes the board and all ${board.subcollections.length} sub-collection${board.subcollections.length === 1 ? "" : "s"} in it. Posts themselves aren't affected. Can't be undone.`}
          confirmLabel={deleting ? "Deleting…" : "Delete"}
          danger
          busy={deleting}
          onConfirm={handleDelete}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
