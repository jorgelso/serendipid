"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface GenerateStudyGuideButtonProps {
  shortcodes: string[];
  sourceLabel: string;
  // Semantic sub-groups (e.g. a theme's micro-clusters, each a shortcode
  // list) for the backend's >MAX_STUDY_GUIDE_POSTS chunking pipeline to
  // pack chunks along — pass whenever the caller actually has that
  // structure (ThemeAccordion, VectorSpaceLegend); omit for a flat idea
  // cluster with no sub-structure (IdeaRow).
  groups?: string[][];
  label?: string;
  className?: string;
}

// One-click study-guide generation for an already-known, fixed set of
// shortcodes (a theme, an idea cluster) — no selection UI needed, unlike
// StudyGuideToolbar's pick-your-own-posts flow. Shared by IdeaRow,
// ThemeAccordion, and VectorSpaceLegend so the POST /api/study-guide +
// navigate-on-success logic isn't duplicated at each call site.
export default function GenerateStudyGuideButton({
  shortcodes,
  sourceLabel,
  groups,
  label = "Generate study guide",
  className,
}: GenerateStudyGuideButtonProps) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "generating" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function generate() {
    setState("generating");
    setMessage(null);
    try {
      const res = await fetch("/api/study-guide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcodes, source_label: sourceLabel, groups }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't generate a study guide.");
      // Generation now runs in the background — data.data is a freshly-
      // created, still-empty collection. Go to the list, which polls and
      // fills in live rather than making the user wait on this page.
      router.push("/study-guides");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't generate a study guide.");
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={generate}
        disabled={state === "generating" || shortcodes.length === 0}
        className={
          className ??
          "shrink-0 rounded-full border border-line text-ink text-xs font-bold px-3 py-1.5 hover:bg-surface-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        }
      >
        {state === "generating" ? "Generating…" : label}
      </button>
      {state === "error" && message && <p className="text-xs text-danger">{message}</p>}
    </span>
  );
}
