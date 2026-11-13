"use client";

import type { ChatSourceDisplayMode } from "@/lib/useChatSourceDisplayMode";

export default function ChatSourceModeToggle({
  mode,
  onChange,
}: {
  mode: ChatSourceDisplayMode;
  onChange: (mode: ChatSourceDisplayMode) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-full border border-line bg-surface p-1 text-xs">
      <button
        type="button"
        onClick={() => onChange("always")}
        className={`px-3 py-1.5 rounded-full font-bold transition-colors ${
          mode === "always" ? "bg-ink text-bg" : "text-ink-muted hover:text-ink"
        }`}
      >
        Always show sources
      </button>
      <button
        type="button"
        onClick={() => onChange("on-demand")}
        className={`px-3 py-1.5 rounded-full font-bold transition-colors ${
          mode === "on-demand" ? "bg-ink text-bg" : "text-ink-muted hover:text-ink"
        }`}
      >
        Show on request
      </button>
    </div>
  );
}
