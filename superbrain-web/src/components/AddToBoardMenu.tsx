"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Board } from "@/types/domain";
import { refreshBoards, useBoards } from "@/lib/useBoards";

interface AddToBoardMenuProps {
  shortcode: string;
  // Compact icon-only trigger for tight spaces (Browse grid cards); the
  // default is a labeled text trigger matching PostDetail's Edit/Delete style.
  compact?: boolean;
}

// Self-contained: fetches/mutates boards itself (useBoards.ts's shared
// fetch-once cache) rather than requiring boards to be prop-drilled down
// through InfiniteFeed/PostCard/PostModal/PostDetail from whichever server
// component first rendered the page. This is what lets the same component
// cover all three "add to board" entry points (Browse cards, the post modal,
// the full post page) without touching those components' data flow.
export default function AddToBoardMenu({ shortcode, compact = false }: AddToBoardMenuProps) {
  const boards = useBoards();
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newBoardName, setNewBoardName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function openMenu() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      const left = Math.min(Math.max(8, rect.right - 272), window.innerWidth - 288);
      setCoords({ top: rect.bottom + 6, left });
    }
    setError(null);
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  const memberCount = (boards ?? []).filter((b) => b.post_ids.includes(shortcode)).length;

  async function toggleBoard(board: Board) {
    setBusyKey(board.id);
    setError(null);
    try {
      const isMember = board.post_ids.includes(shortcode);
      const res = await fetch(`/api/boards/${board.id}/posts/${shortcode}`, {
        method: isMember ? "DELETE" : "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't update board.");
      await refreshBoards();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update board.");
    } finally {
      setBusyKey(null);
    }
  }

  async function toggleSubcollection(boardId: string, sub: { id: string; post_ids: string[] }) {
    setBusyKey(sub.id);
    setError(null);
    try {
      const isMember = sub.post_ids.includes(shortcode);
      const res = await fetch(`/api/boards/${boardId}/subcollections/${sub.id}/posts/${shortcode}`, {
        method: isMember ? "DELETE" : "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't update subcollection.");
      await refreshBoards();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update subcollection.");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleCreateBoard(e: React.FormEvent) {
    e.preventDefault();
    const name = newBoardName.trim();
    if (!name) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/boards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't create board.");
      setNewBoardName("");
      await refreshBoards();
      const created: Board = data.data;
      await toggleBoard(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create board.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? setOpen(false) : openMenu())}
        className={
          compact
            ? "rounded-full bg-ink/70 text-bg text-[11px] font-bold px-2.5 py-1 backdrop-blur-sm hover:opacity-85 transition-opacity"
            : "text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
        }
      >
        {memberCount > 0 ? `📌 On ${memberCount} board${memberCount === 1 ? "" : "s"}` : "📌 Add to board"}
      </button>

      {open &&
        coords &&
        createPortal(
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <div
              className="fixed z-50 w-72 max-h-[70vh] overflow-y-auto rounded-2xl border border-line bg-surface shadow-xl p-3"
              style={{ top: coords.top, left: coords.left }}
            >
              <p className="px-1 mb-1 text-[11px] font-bold uppercase tracking-wide text-ink-muted">Boards</p>

              {boards === null && <p className="px-1 text-xs text-ink-muted">Loading…</p>}
              {boards !== null && boards.length === 0 && (
                <p className="px-1 text-xs text-ink-muted">No boards yet — create one below.</p>
              )}

              <div className="flex flex-col gap-0.5">
                {(boards ?? []).map((board) => (
                  <div key={board.id}>
                    <label className="flex items-center gap-2 px-1 py-1.5 rounded-lg hover:bg-surface-2 cursor-pointer text-sm">
                      <input
                        type="checkbox"
                        checked={board.post_ids.includes(shortcode)}
                        disabled={busyKey === board.id}
                        onChange={() => toggleBoard(board)}
                        className="h-4 w-4 accent-ink"
                      />
                      <span className="truncate">
                        {board.icon ?? "🗂️"} {board.name}
                      </span>
                    </label>
                    {board.subcollections.length > 0 && (
                      <div className="ml-6 flex flex-col gap-0.5">
                        {board.subcollections.map((sub) => (
                          <label
                            key={sub.id}
                            className="flex items-center gap-2 px-1 py-1 rounded-lg hover:bg-surface-2 cursor-pointer text-xs text-ink-muted"
                          >
                            <input
                              type="checkbox"
                              checked={sub.post_ids.includes(shortcode)}
                              disabled={busyKey === sub.id}
                              onChange={() => toggleSubcollection(board.id, sub)}
                              className="h-3.5 w-3.5 accent-ink"
                            />
                            <span className="truncate">
                              {sub.icon ?? "📁"} {sub.name}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <form onSubmit={handleCreateBoard} className="mt-2 pt-2 border-t border-line flex items-center gap-1.5">
                <input
                  type="text"
                  value={newBoardName}
                  onChange={(e) => setNewBoardName(e.target.value)}
                  placeholder="New board name"
                  disabled={creating}
                  className="flex-1 min-w-0 rounded-lg border border-line bg-bg px-2 py-1.5 text-xs"
                />
                <button
                  type="submit"
                  disabled={creating || !newBoardName.trim()}
                  className="shrink-0 rounded-lg bg-ink text-bg text-xs font-bold px-2.5 py-1.5 disabled:opacity-50"
                >
                  {creating ? "…" : "+ Add"}
                </button>
              </form>

              {error && <p className="mt-1.5 px-1 text-[11px] text-danger">{error}</p>}
            </div>
          </>,
          document.body
        )}
    </>
  );
}
