"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { BatchCheckResponse } from "@/types/domain";

// Manual trigger for ANALYSIS_MODE=batch's completion check — checks ALL
// THREE batch pipelines from one click: first-analysis (backend/core/
// batch_processor.py, via /api/batches/check), rescan (backend/core/
// rescan_batch_processor.py, via /api/rescan-batches/check) and the
// eloquence backfill (backend/core/eloquence_batch_processor.py, via
// /api/eloquence-batches/check), since from the user's perspective "check
// batches" means all of them, even though the backend deliberately tracks
// each with its own table/lock.
// The backend also checks each one automatically on its own startup, but
// there's no periodic polling on its own, so this is how a batch-pending
// post gets picked up without restarting the backend. Harmless, near-instant
// no-op when ANALYSIS_MODE=immediate (no batch jobs exist), so it's always
// rendered rather than conditionally shown.
//
// The auto-poll toggle is purely a client-side convenience on top of that
// same manual endpoint — it does NOT turn on any server-side polling (the
// backend still only checks on startup or when actually called). Flipping
// the toggle on by itself does nothing; clicking the button while it's on is
// what starts a 10-minute setInterval that keeps calling the same check the
// button always called, until the toggle is switched back off (or the page
// is closed/reloaded — this state isn't persisted).
const AUTO_POLL_INTERVAL_MS = 10 * 60 * 1000;

export default function CheckBatchesButton() {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [autoPoll, setAutoPoll] = useState(false);
  const [polling, setPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setPolling(false);
  }

  // Cleanup-only effect (unmount) so navigating away doesn't leave a stray
  // interval running against an unmounted component. Switching the toggle
  // off is handled directly in its click handler below, not here — it's a
  // discrete user action, not something to react to via an effect.
  useEffect(() => stopPolling, []);

  async function runCheck() {
    setState("loading");
    setMessage(null);
    try {
      const [firstAnalysisRes, rescanRes, eloquenceRes] = await Promise.all([
        fetch("/api/batches/check", { method: "POST" }),
        fetch("/api/rescan-batches/check", { method: "POST" }),
        fetch("/api/eloquence-batches/check", { method: "POST" }),
      ]);
      const [firstAnalysisData, rescanData, eloquenceData]: (BatchCheckResponse & { error?: string })[] =
        await Promise.all([firstAnalysisRes.json(), rescanRes.json(), eloquenceRes.json()]);
      if (!firstAnalysisRes.ok) throw new Error(firstAnalysisData.error ?? "Batch check failed.");
      if (!rescanRes.ok) throw new Error(rescanData.error ?? "Rescan batch check failed.");
      if (!eloquenceRes.ok) throw new Error(eloquenceData.error ?? "Eloquence batch check failed.");

      setState("idle");
      const finalizedCount =
        (firstAnalysisData.finalized?.length ?? 0) +
        (rescanData.finalized?.length ?? 0) +
        (eloquenceData.scored?.length ?? 0);
      setMessage(finalizedCount > 0 ? `${finalizedCount} post(s) finished.` : null);
      router.refresh();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Batch check failed.");
      // Keep polling even after a transient failure — one bad tick (e.g. a
      // dropped connection) shouldn't silently end a 10-minute watch the
      // user explicitly started. They can still switch the toggle off.
    }
  }

  function handleClick() {
    runCheck();
    if (autoPoll && intervalRef.current === null) {
      intervalRef.current = setInterval(runCheck, AUTO_POLL_INTERVAL_MS);
      setPolling(true);
    }
  }

  return (
    <div className="relative flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={state === "loading"}
        className="rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:text-coral-ink hover:border-coral transition-colors disabled:opacity-50"
      >
        {state === "loading" ? "Checking…" : "📦 Check batches"}
      </button>

      <button
        type="button"
        role="switch"
        aria-checked={autoPoll}
        aria-label="Auto-check batches every 10 minutes"
        title={autoPoll ? "Auto-check every 10 min: on" : "Auto-check every 10 min: off"}
        onClick={() => {
          const next = !autoPoll;
          setAutoPoll(next);
          if (!next) stopPolling();
        }}
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          autoPoll ? "bg-coral" : "bg-line"
        }`}
      >
        <span
          className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
            autoPoll ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>

      {(message || polling) && (
        <p
          className={`absolute right-0 top-full mt-2 w-56 text-xs text-right ${
            state === "error" ? "text-danger" : "text-ink-muted"
          }`}
        >
          {message && <span className="block">{message}</span>}
          {polling && (
            <span className="block text-ink-muted">Auto-checking every 10 min…</span>
          )}
        </p>
      )}
    </div>
  );
}
