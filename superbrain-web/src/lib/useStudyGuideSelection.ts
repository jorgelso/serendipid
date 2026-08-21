"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export type StudyGuideGenerateState = "idle" | "generating" | "error";

// Shared selection + generation state for turning a picked set of posts into
// an on-demand study guide (POST /api/study-guide) — same shape as
// EloquentFeed.tsx's selection state, but generalized so both the home feed
// and search results can mount their own selectable UI against one
// implementation instead of duplicating this logic. sourceLabel is stored on
// the resulting study_guides row (backend/core/database.py) purely for
// display — "Home feed selection", `Search: "cold email"`, etc.
export function useStudyGuideSelection(sourceLabel?: string) {
  const router = useRouter();
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [generateState, setGenerateState] = useState<StudyGuideGenerateState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  function toggleSelect(shortcode: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(shortcode)) next.delete(shortcode);
      else next.add(shortcode);
      return next;
    });
  }

  function stopSelecting() {
    setSelecting(false);
    setSelected(new Set());
    setGenerateState("idle");
    setMessage(null);
  }

  async function generate() {
    setGenerateState("generating");
    setMessage(null);
    try {
      const res = await fetch("/api/study-guide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcodes: Array.from(selected), source_label: sourceLabel }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't generate a study guide.");
      stopSelecting();
      // Generation now runs in the background (see apiClient.ts's
      // generateStudyGuide()) — data.data is a freshly-created, still-empty
      // collection, not a finished guide. Go to the list, which polls and
      // fills in live rather than making the user wait on this page.
      router.push("/study-guides");
    } catch (err) {
      setGenerateState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't generate a study guide.");
    }
  }

  return {
    selecting,
    setSelecting,
    selected,
    toggleSelect,
    stopSelecting,
    generateState,
    message,
    generate,
  };
}
