"use client";

import type { ChatThread } from "@/types/domain";

export default function ChatThreadSidebar({
  threads,
  activeThreadId,
  onSelect,
  onNew,
  onDelete,
}: {
  threads: ChatThread[];
  activeThreadId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="md:w-72 shrink-0 border-line md:border-r flex flex-col">
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="w-full rounded-full bg-coral px-4 py-2.5 text-sm font-display font-semibold text-white hover:opacity-90 transition-opacity"
        >
          + New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-1 max-h-48 md:max-h-none">
        {threads.length === 0 && (
          <p className="px-2 py-4 text-xs text-ink-muted text-center">No conversations yet.</p>
        )}
        {threads.map((thread) => (
          <div
            key={thread.id}
            className={`group flex items-center gap-1 rounded-xl px-3 py-2 cursor-pointer transition-colors ${
              thread.id === activeThreadId ? "bg-surface-2" : "hover:bg-surface-2"
            }`}
            onClick={() => onSelect(thread.id)}
          >
            <span className="flex-1 text-sm truncate">{thread.title || "New conversation"}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(thread.id);
              }}
              className="opacity-0 group-hover:opacity-100 text-ink-muted hover:text-coral-ink transition-opacity text-xs px-1"
              aria-label="Delete conversation"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
