"use client";

import { useState } from "react";
import type { ChatSource } from "@/types/domain";
import type { ChatSourceDisplayMode } from "@/lib/useChatSourceDisplayMode";

export default function ChatSourceCards({
  sources,
  mode,
}: {
  sources: ChatSource[];
  mode: ChatSourceDisplayMode;
}) {
  const [expanded, setExpanded] = useState(mode === "always");
  // Re-sync when the user flips the global setting, without clobbering a
  // manual per-message toggle on every unrelated re-render — adjusted during
  // render (React's recommended pattern for state derived from a prop),
  // not in an effect, since this needs to happen before paint.
  const [prevMode, setPrevMode] = useState(mode);
  if (mode !== prevMode) {
    setPrevMode(mode);
    setExpanded(mode === "always");
  }

  if (sources.length === 0) return null;

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mt-2 text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
      >
        Show sources ({sources.length})
      </button>
    );
  }

  return (
    <div className="mt-2">
      {mode === "on-demand" && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mb-2 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
        >
          Hide sources
        </button>
      )}
      <div className="flex flex-wrap gap-2">
        {sources.map((source) => (
          <a
            key={source.shortcode}
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-2xl border border-line bg-surface pr-3 hover:-translate-y-0.5 transition-transform"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/api/thumbnail/${source.shortcode}`}
              alt=""
              className="h-10 w-10 rounded-l-2xl object-cover shrink-0 bg-surface-2"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
            <div className="py-1.5 max-w-[180px]">
              <p className="text-[12px] font-bold leading-tight line-clamp-1">
                {source.title || "Untitled reel"}
              </p>
              <p className="text-[11px] text-ink-muted">
                @{source.username} · {(source.similarity * 100).toFixed(0)}% match
              </p>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
