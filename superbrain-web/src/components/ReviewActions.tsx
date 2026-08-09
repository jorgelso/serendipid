"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface ReviewActionsProps {
  shortcode: string;
  url: string;
}

type State = "idle" | "reanalyzing" | "marking" | "done" | "error";

export default function ReviewActions({ shortcode, url }: ReviewActionsProps) {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function post(path: string, body: unknown, fallbackError: string) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? fallbackError);
    return data;
  }

  async function handleReanalyze() {
    setState("reanalyzing");
    setMessage(null);
    try {
      await post("/api/reanalyze", { url }, "Re-analysis failed.");
      setState("done");
      setMessage("Re-analyzed — refresh to see the update.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Re-analysis failed.");
    }
  }

  async function handleMarkReviewed() {
    setState("marking");
    setMessage(null);
    try {
      await post("/api/mark-reviewed", { shortcode }, "Couldn't mark this reviewed.");
      setState("done");
      setMessage("Marked reviewed.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't mark this reviewed.");
    }
  }

  if (state === "done") {
    return (
      <div className="mt-3 rounded-xl bg-yellow-soft px-3 py-2 text-xs font-bold text-yellow-ink flex items-center justify-between gap-2">
        <span>{message}</span>
        <button onClick={() => router.refresh()} className="underline shrink-0">
          Refresh
        </button>
      </div>
    );
  }

  const busy = state === "reanalyzing" || state === "marking";

  return (
    <div className="mt-3 rounded-xl bg-yellow-soft px-3 py-2.5">
      <p className="text-xs font-bold text-yellow-ink mb-2">Categorized under the old system</p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={handleReanalyze}
          disabled={busy}
          className="rounded-full bg-yellow-ink text-bg text-[11px] font-bold px-3 py-1.5 disabled:opacity-50"
        >
          {state === "reanalyzing" ? "Re-analyzing… (can take a few minutes)" : "Re-run analysis"}
        </button>
        <button
          onClick={handleMarkReviewed}
          disabled={busy}
          className="rounded-full border border-yellow-ink text-yellow-ink text-[11px] font-bold px-3 py-1.5 disabled:opacity-50"
        >
          {state === "marking" ? "Marking…" : "Keep as is"}
        </button>
      </div>
      {state === "error" && <p className="mt-2 text-xs text-danger">{message}</p>}
    </div>
  );
}
