"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Board, BoardSubcollection } from "@/types/domain";
import { refreshBoards } from "@/lib/useBoards";
import ConfirmDialog from "./ConfirmDialog";
import BoardPostsGrid from "./BoardPostsGrid";
import PostPicker, { type LightPost } from "./PostPicker";

interface BoardDetailProps {
  board: Board;
  allPosts: LightPost[];
}

export default function BoardDetail({ board, allPosts }: BoardDetailProps) {
  const router = useRouter();
  const postsByShortcode = useMemo(() => new Map(allPosts.map((p) => [p.shortcode, p])), [allPosts]);

  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(board.name);
  const [iconDraft, setIconDraft] = useState(board.icon ?? "🗂️");
  const [savingName, setSavingName] = useState(false);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deletingBoard, setDeletingBoard] = useState(false);

  const [removingShortcode, setRemovingShortcode] = useState<string | null>(null);
  const [pickerFor, setPickerFor] = useState<"board" | string | null>(null); // "board" or a subcollection id

  const [creatingSub, setCreatingSub] = useState(false);
  const [newSubName, setNewSubName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function saveName(e: React.FormEvent) {
    e.preventDefault();
    setSavingName(true);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameDraft.trim() || board.name, icon: iconDraft.trim() || board.icon }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't rename board.");
      await refreshBoards();
      router.refresh();
      setRenaming(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't rename board.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleDeleteBoard() {
    setDeletingBoard(true);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete board.");
      await refreshBoards();
      router.push("/boards");
      router.refresh();
    } catch (err) {
      setDeletingBoard(false);
      setConfirmingDelete(false);
      setError(err instanceof Error ? err.message : "Couldn't delete board.");
    }
  }

  async function addPostToBoard(shortcode: string) {
    const res = await fetch(`/api/boards/${board.id}/posts/${shortcode}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? "Couldn't add post.");
    await refreshBoards();
    router.refresh();
  }

  async function removePostFromBoard(shortcode: string) {
    setRemovingShortcode(shortcode);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}/posts/${shortcode}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't remove post.");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove post.");
    } finally {
      setRemovingShortcode(null);
    }
  }

  async function addPostToSub(subId: string, shortcode: string) {
    const res = await fetch(`/api/boards/${board.id}/subcollections/${subId}/posts/${shortcode}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? "Couldn't add post.");
    await refreshBoards();
    router.refresh();
  }

  async function removePostFromSub(subId: string, shortcode: string) {
    setRemovingShortcode(shortcode);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}/subcollections/${subId}/posts/${shortcode}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't remove post.");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove post.");
    } finally {
      setRemovingShortcode(null);
    }
  }

  async function handleCreateSub(e: React.FormEvent) {
    e.preventDefault();
    const name = newSubName.trim();
    if (!name) return;
    setCreatingSub(true);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}/subcollections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't create sub-collection.");
      setNewSubName("");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create sub-collection.");
    } finally {
      setCreatingSub(false);
    }
  }

  return (
    <div>
      <Link href="/boards" className="text-xs font-bold text-ink-muted hover:text-coral-ink transition-colors">
        ← All boards
      </Link>

      <div className="mt-2 flex items-start justify-between gap-3">
        {!renaming ? (
          <>
            <h1 className="font-display font-semibold text-3xl">
              {board.icon ?? "🗂️"} {board.name}
            </h1>
            <div className="shrink-0 flex items-center gap-3">
              <button
                onClick={() => {
                  setNameDraft(board.name);
                  setIconDraft(board.icon ?? "🗂️");
                  setRenaming(true);
                }}
                className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
              >
                ✏️ Rename
              </button>
              <button
                onClick={() => setConfirmingDelete(true)}
                className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
              >
                🗑 Delete
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={saveName} className="flex items-center gap-2 w-full">
            <input
              type="text"
              value={iconDraft}
              onChange={(e) => setIconDraft(e.target.value)}
              maxLength={4}
              className="w-14 shrink-0 rounded-full border border-line bg-surface px-3 py-2 text-center text-lg"
            />
            <input
              type="text"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              className="flex-1 min-w-0 rounded-full border border-line bg-surface px-4 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={savingName}
              className="shrink-0 rounded-full bg-ink text-bg font-bold text-xs px-4 py-2 disabled:opacity-50"
            >
              {savingName ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => setRenaming(false)}
              className="shrink-0 text-xs font-bold text-ink-muted"
            >
              Cancel
            </button>
          </form>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <section className="mt-6">
        <div className="flex items-center justify-between gap-2 mb-3">
          <h2 className="font-display font-semibold text-lg">
            Posts <span className="text-ink-muted font-normal text-sm">({board.post_ids.length})</span>
          </h2>
          <button
            type="button"
            onClick={() => setPickerFor("board")}
            className="rounded-full border border-line text-xs font-bold px-3.5 py-1.5 hover:bg-surface-2 transition-colors"
          >
            + Add posts
          </button>
        </div>
        <BoardPostsGrid
          shortcodes={board.post_ids}
          postsByShortcode={postsByShortcode}
          onRemove={removePostFromBoard}
          removingShortcode={removingShortcode}
        />
      </section>

      <section className="mt-10">
        <h2 className="font-display font-semibold text-lg mb-3">Sub-collections</h2>

        <form onSubmit={handleCreateSub} className="mb-4 flex items-center gap-2 max-w-sm">
          <input
            type="text"
            value={newSubName}
            onChange={(e) => setNewSubName(e.target.value)}
            placeholder="New sub-collection name"
            disabled={creatingSub}
            className="flex-1 min-w-0 rounded-full border border-line bg-surface px-4 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={creatingSub || !newSubName.trim()}
            className="shrink-0 rounded-full bg-ink text-bg font-bold text-xs px-4 py-2 disabled:opacity-50"
          >
            {creatingSub ? "Creating…" : "+ Create"}
          </button>
        </form>

        {board.subcollections.length === 0 && (
          <p className="text-sm text-ink-muted">No sub-collections yet.</p>
        )}

        <div className="flex flex-col gap-4">
          {board.subcollections.map((sub) => (
            <SubcollectionSection
              key={sub.id}
              boardId={board.id}
              sub={sub}
              postsByShortcode={postsByShortcode}
              removingShortcode={removingShortcode}
              onAddPost={(shortcode) => addPostToSub(sub.id, shortcode)}
              onRemovePost={(shortcode) => removePostFromSub(sub.id, shortcode)}
              onOpenPicker={() => setPickerFor(sub.id)}
              onError={setError}
            />
          ))}
        </div>
      </section>

      {pickerFor && (
        <PostPicker
          title={pickerFor === "board" ? `Add posts to ${board.name}` : "Add posts to sub-collection"}
          allPosts={allPosts}
          excludeShortcodes={
            pickerFor === "board"
              ? board.post_ids
              : board.subcollections.find((s) => s.id === pickerFor)?.post_ids ?? []
          }
          onAdd={async (shortcode) => {
            try {
              if (pickerFor === "board") {
                await addPostToBoard(shortcode);
              } else {
                await addPostToSub(pickerFor, shortcode);
              }
            } catch (err) {
              setError(err instanceof Error ? err.message : "Couldn't add post.");
            }
          }}
          onClose={() => setPickerFor(null)}
        />
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete "${board.name}"?`}
          message={`This deletes the board and all ${board.subcollections.length} sub-collection${board.subcollections.length === 1 ? "" : "s"} in it. Posts themselves aren't affected. Can't be undone.`}
          confirmLabel={deletingBoard ? "Deleting…" : "Delete"}
          danger
          busy={deletingBoard}
          onConfirm={handleDeleteBoard}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}

interface SubcollectionSectionProps {
  boardId: string;
  sub: BoardSubcollection;
  postsByShortcode: Map<string, LightPost>;
  removingShortcode: string | null;
  onAddPost: (shortcode: string) => Promise<void>;
  onRemovePost: (shortcode: string) => Promise<void>;
  onOpenPicker: () => void;
  onError: (message: string) => void;
}

function SubcollectionSection({
  boardId,
  sub,
  postsByShortcode,
  removingShortcode,
  onRemovePost,
  onOpenPicker,
  onError,
}: SubcollectionSectionProps) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(sub.name);
  const [iconDraft, setIconDraft] = useState(sub.icon ?? "📁");
  const [savingName, setSavingName] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function saveName(e: React.FormEvent) {
    e.preventDefault();
    setSavingName(true);
    try {
      const res = await fetch(`/api/boards/${boardId}/subcollections/${sub.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameDraft.trim() || sub.name, icon: iconDraft.trim() || sub.icon }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't rename sub-collection.");
      await refreshBoards();
      router.refresh();
      setRenaming(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Couldn't rename sub-collection.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      const res = await fetch(`/api/boards/${boardId}/subcollections/${sub.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete sub-collection.");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setDeleting(false);
      setConfirmingDelete(false);
      onError(err instanceof Error ? err.message : "Couldn't delete sub-collection.");
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        {!renaming ? (
          <>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="min-w-0 flex items-center gap-2 text-left"
            >
              <span className="text-ink-muted text-xs">{expanded ? "▾" : "▸"}</span>
              <span className="font-display font-semibold text-sm truncate">
                {sub.icon ?? "📁"} {sub.name}
              </span>
              <span className="text-xs text-ink-muted shrink-0">
                ({sub.post_ids.length} post{sub.post_ids.length === 1 ? "" : "s"})
              </span>
            </button>
            <div className="shrink-0 flex items-center gap-3">
              <button
                onClick={onOpenPicker}
                className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
              >
                + Add posts
              </button>
              <button
                onClick={() => {
                  setNameDraft(sub.name);
                  setIconDraft(sub.icon ?? "📁");
                  setRenaming(true);
                }}
                className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
              >
                ✏️
              </button>
              <button
                onClick={() => setConfirmingDelete(true)}
                className="text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
              >
                🗑
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={saveName} className="flex items-center gap-2 w-full">
            <input
              type="text"
              value={iconDraft}
              onChange={(e) => setIconDraft(e.target.value)}
              maxLength={4}
              className="w-12 shrink-0 rounded-full border border-line bg-bg px-2 py-1.5 text-center"
            />
            <input
              type="text"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              className="flex-1 min-w-0 rounded-full border border-line bg-bg px-3 py-1.5 text-sm"
            />
            <button
              type="submit"
              disabled={savingName}
              className="shrink-0 rounded-full bg-ink text-bg font-bold text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {savingName ? "…" : "Save"}
            </button>
            <button type="button" onClick={() => setRenaming(false)} className="shrink-0 text-xs text-ink-muted">
              Cancel
            </button>
          </form>
        )}
      </div>

      {expanded && !renaming && (
        <div className="mt-3">
          <BoardPostsGrid
            shortcodes={sub.post_ids}
            postsByShortcode={postsByShortcode}
            onRemove={onRemovePost}
            removingShortcode={removingShortcode}
          />
        </div>
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete "${sub.name}"?`}
          message="This deletes the sub-collection. Its parent board and any other sub-collections are untouched. Posts themselves aren't affected. Can't be undone."
          confirmLabel={deleting ? "Deleting…" : "Delete"}
          danger
          busy={deleting}
          onConfirm={handleDelete}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}
