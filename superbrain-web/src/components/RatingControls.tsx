"use client";

import { useState } from "react";
import type { RatingTier } from "@/types/domain";

interface RatingControlsProps {
  shortcode: string;
  enjoymentRating: RatingTier;
  perceivedImportanceRating: RatingTier;
  onSaved: (edits: { enjoyment_rating?: RatingTier; perceived_importance_rating?: RatingTier }) => void;
}

type Field = "enjoyment_rating" | "perceived_importance_rating";

// Netflix-style tri-state: null (default) -> 'liked' -> 'loved', clicking the
// currently-active tier again resets to null. Two independent axes — this is
// the user's own subjective judgment, distinct from the AI-scored
// `importance` badge shown elsewhere, and both feed the Home recommendation
// engine (src/lib/recommendations.ts) alongside implicit view/search signals.
export default function RatingControls({
  shortcode,
  enjoymentRating,
  perceivedImportanceRating,
  onSaved,
}: RatingControlsProps) {
  const [saving, setSaving] = useState<Field | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function setRating(field: Field, tier: "liked" | "loved", current: RatingTier) {
    const next: RatingTier = current === tier ? null : tier;
    setSaving(field);
    setError(null);
    try {
      const res = await fetch("/api/update-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shortcode, [field]: next }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't save rating.");
      onSaved({ [field]: next });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save rating.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-4">
      <RatingGroup
        label="Enjoyment"
        field="enjoyment_rating"
        current={enjoymentRating}
        likedEmoji="🙂"
        lovedEmoji="😍"
        activeClass="bg-coral-ink text-bg"
        idleClass="border border-line text-ink-muted hover:text-ink"
        busy={saving === "enjoyment_rating"}
        onPick={(tier) => setRating("enjoyment_rating", tier, enjoymentRating)}
      />
      <RatingGroup
        label="Matters to me"
        field="perceived_importance_rating"
        current={perceivedImportanceRating}
        likedEmoji="👍"
        lovedEmoji="⭐"
        activeClass="bg-teal-ink text-bg"
        idleClass="border border-line text-ink-muted hover:text-ink"
        busy={saving === "perceived_importance_rating"}
        onPick={(tier) => setRating("perceived_importance_rating", tier, perceivedImportanceRating)}
      />
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}

function RatingGroup({
  label,
  current,
  likedEmoji,
  lovedEmoji,
  activeClass,
  idleClass,
  busy,
  onPick,
}: {
  label: string;
  field: Field;
  current: RatingTier;
  likedEmoji: string;
  lovedEmoji: string;
  activeClass: string;
  idleClass: string;
  busy: boolean;
  onPick: (tier: "liked" | "loved") => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] font-bold uppercase tracking-wide text-ink-muted">{label}</span>
      <button
        type="button"
        disabled={busy}
        onClick={() => onPick("liked")}
        aria-pressed={current === "liked"}
        title="Liked it"
        className={`rounded-full text-[11px] font-bold px-2.5 py-1 disabled:opacity-50 transition-colors ${
          current === "liked" ? activeClass : idleClass
        }`}
      >
        {likedEmoji} Liked
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => onPick("loved")}
        aria-pressed={current === "loved"}
        title="Loved it"
        className={`rounded-full text-[11px] font-bold px-2.5 py-1 disabled:opacity-50 transition-colors ${
          current === "loved" ? activeClass : idleClass
        }`}
      >
        {lovedEmoji} Loved
      </button>
    </div>
  );
}
