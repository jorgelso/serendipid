"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { refreshBoards } from "@/lib/useBoards";

export default function CreateBoardForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("🗂️");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/boards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed, icon: icon.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't create board.");
      setName("");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create board.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        type="text"
        value={icon}
        onChange={(e) => setIcon(e.target.value)}
        aria-label="Board icon"
        maxLength={4}
        className="w-14 shrink-0 rounded-full border border-line bg-surface px-3 py-2.5 text-center text-lg"
      />
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="New board name"
        disabled={busy}
        className="flex-1 min-w-0 rounded-full border border-line bg-surface px-4 py-2.5 text-sm"
      />
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="shrink-0 rounded-full bg-ink text-bg font-display font-semibold text-sm px-5 py-2.5 hover:opacity-85 transition-opacity disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create"}
      </button>
      {error && <span className="text-xs text-danger">{error}</span>}
    </form>
  );
}
