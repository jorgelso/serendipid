"use client";

import { useRouter } from "next/navigation";

type Tutorial = "" | "yes" | "no";
type Reviewed = "" | "yes" | "no";

interface EloquenceFiltersProps {
  tutorial: Tutorial;
  reviewed: Reviewed;
}

const TUTORIAL_TABS: { value: Tutorial; label: string }[] = [
  { value: "", label: "All" },
  { value: "no", label: "Non-tutorials" },
  { value: "yes", label: "Tutorials" },
];

// Human-review state (PostCard's per-card Approve/Reject on this page).
// "Unreviewed" is the review queue: only posts a fresh scoring run added
// that nobody has confirmed yet.
const REVIEWED_TABS: { value: Reviewed; label: string }[] = [
  { value: "", label: "All" },
  { value: "no", label: "Unreviewed" },
  { value: "yes", label: "Approved" },
];

function SegmentedControl<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  label: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex items-center gap-1 rounded-full border border-line bg-surface p-1"
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value || "all"}
            type="button"
            onClick={() => onChange(tab.value)}
            aria-pressed={active}
            className={`rounded-full px-4 py-1.5 text-sm font-bold transition-colors cursor-pointer ${
              active ? "bg-ink text-bg" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export default function EloquenceFilters({ tutorial, reviewed }: EloquenceFiltersProps) {
  const router = useRouter();

  function navigate(nextTutorial: Tutorial, nextReviewed: Reviewed) {
    const query = new URLSearchParams();
    if (nextTutorial) query.set("tutorial", nextTutorial);
    if (nextReviewed) query.set("reviewed", nextReviewed);
    const qs = query.toString();
    router.push(`/eloquent${qs ? `?${qs}` : ""}`);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <SegmentedControl
        label="Delivery style"
        tabs={TUTORIAL_TABS}
        value={tutorial}
        onChange={(next) => navigate(next, reviewed)}
      />
      <SegmentedControl
        label="Review state"
        tabs={REVIEWED_TABS}
        value={reviewed}
        onChange={(next) => navigate(tutorial, next)}
      />
    </div>
  );
}
