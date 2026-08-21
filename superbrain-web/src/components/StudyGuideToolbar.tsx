"use client";

import type { StudyGuideGenerateState } from "@/lib/useStudyGuideSelection";

interface StudyGuideToolbarProps {
  selecting: boolean;
  selectedCount: number;
  generateState: StudyGuideGenerateState;
  message: string | null;
  onToggleSelecting: () => void;
  onGenerate: () => void;
}

// Selection toolbar for turning a chosen set of posts into an on-demand
// study guide — same "Select" toggle + bulk-action button shape as
// EloquentFeed.tsx's eloquence-override toolbar, reused on the home feed
// and search results against src/lib/useStudyGuideSelection.ts's shared state.
export default function StudyGuideToolbar({
  selecting,
  selectedCount,
  generateState,
  message,
  onToggleSelecting,
  onGenerate,
}: StudyGuideToolbarProps) {
  return (
    <div className="mb-4 flex items-center gap-2 flex-wrap">
      <button
        type="button"
        onClick={onToggleSelecting}
        className="rounded-full border border-line text-ink text-sm font-bold px-4 py-1.5 hover:bg-surface-2 transition-colors cursor-pointer"
      >
        {selecting ? "Cancel" : "Select for study guide"}
      </button>

      {selecting && (
        <button
          type="button"
          onClick={onGenerate}
          disabled={selectedCount === 0 || generateState === "generating"}
          className="rounded-full bg-ink text-bg text-sm font-bold px-4 py-1.5 hover:opacity-85 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {generateState === "generating"
            ? "Generating…"
            : `Generate study guide${selectedCount > 0 ? ` (${selectedCount})` : ""}`}
        </button>
      )}

      {generateState === "error" && message && <p className="text-sm text-danger">{message}</p>}
    </div>
  );
}
