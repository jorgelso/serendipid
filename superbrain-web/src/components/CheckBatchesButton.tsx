"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { BatchCheckResponse } from "@/types/domain";

// Manual trigger for ANALYSIS_MODE=batch's completion check — checks BOTH
// the first-analysis pipeline (backend/core/batch_processor.py, via
// /api/batches/check) and the separate rescan pipeline (backend/core/
// rescan_batch_processor.py, via /api/rescan-batches/check) from one click,
// since from the user's perspective "check batches" means all of them, even
// though the backend deliberately tracks the two with separate tables/locks.
// The backend also checks each one automatically on its own startup, but
// there's no periodic polling, so this is how a batch-pending post gets
// picked up without restarting the backend. Harmless, near-instant no-op
// when ANALYSIS_MODE=immediate (no batch jobs exist), so it's always
// rendered rather than conditionally shown.
export default function CheckBatchesButton() {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleClick() {
    setState("loading");
    setMessage(null);
    try {
      const [firstAnalysisRes, rescanRes] = await Promise.all([
        fetch("/api/batches/check", { method: "POST" }),
        fetch("/api/rescan-batches/check", { method: "POST" }),
      ]);
      const [firstAnalysisData, rescanData]: (BatchCheckResponse & { error?: string })[] =
        await Promise.all([firstAnalysisRes.json(), rescanRes.json()]);
      if (!firstAnalysisRes.ok) throw new Error(firstAnalysisData.error ?? "Batch check failed.");
      if (!rescanRes.ok) throw new Error(rescanData.error ?? "Rescan batch check failed.");

      setState("idle");
      const finalizedCount =
        (firstAnalysisData.finalized?.length ?? 0) + (rescanData.finalized?.length ?? 0);
      setMessage(finalizedCount > 0 ? `${finalizedCount} post(s) finished.` : null);
      router.refresh();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Batch check failed.");
    }
  }

  return (
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={state === "loading"}
        className="rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:text-coral-ink hover:border-coral transition-colors disabled:opacity-50"
      >
        {state === "loading" ? "Checking…" : "📦 Check batches"}
      </button>
      {message && (
        <p
          className={`absolute right-0 mt-2 w-56 text-xs text-right ${
            state === "error" ? "text-danger" : "text-ink-muted"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
