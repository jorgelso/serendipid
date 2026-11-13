"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface ReanalyzeButtonProps {
  url: string;
  label?: string;
  className?: string;
}

type State = "idle" | "loading" | "done" | "error";

const DEFAULT_CLASS =
  "rounded-full bg-yellow-ink text-bg text-[11px] font-bold px-3 py-1.5 disabled:opacity-50";

// Shared by ReviewActions ("Re-run analysis" for stale-taxonomy posts) and
// MediaViewer ("Re-fetch video" for posts missing their local download) —
// both call the same POST /api/reanalyze (force:true) under the hood.
export default function ReanalyzeButton({ url, label = "Re-run analysis", className }: ReanalyzeButtonProps) {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleClick() {
    setState("loading");
    setMessage(null);
    try {
      const res = await fetch("/api/reanalyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Re-analysis failed.");
      setState("done");
      setMessage("Done — refresh to see the update.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Re-analysis failed.");
    }
  }

  if (state === "done") {
    return (
      <div className="flex items-center gap-2 text-xs font-bold text-yellow-ink">
        <span>{message}</span>
        <button onClick={() => router.refresh()} className="underline">
          Refresh
        </button>
      </div>
    );
  }

  return (
    <div>
      <button onClick={handleClick} disabled={state === "loading"} className={className ?? DEFAULT_CLASS}>
        {state === "loading" ? "Re-analyzing… (can take a few minutes)" : label}
      </button>
      {state === "error" && <p className="mt-1 text-xs text-danger">{message}</p>}
    </div>
  );
}
