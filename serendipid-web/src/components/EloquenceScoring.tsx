"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { EloquenceCandidatesResponse, EloquenceScoringJob } from "@/types/domain";

// Admin-panel front end for scripts/score_eloquence.py. Deliberately a
// two-step flow rather than one "score" button: the candidate count is
// shown first (GET /api/eloquence-scoring/candidates), then the user picks
// how many of them to spend LLM calls on — a typed number, or all of them —
// because a first run against a big library can easily be 1000+ posts and
// nobody wants to commit to that in one click.
//
// Progress is polled from the backend's in-memory job (see api.py's
// _eloquence_score_job) rather than streamed. In ANALYSIS_MODE=batch the
// job completes as soon as the OpenAI Batch jobs are submitted; the
// verdicts then land via "Check batches", which is why that case gets its
// own hint below.
const POLL_INTERVAL_MS = 3000;
const DEFAULT_LIMIT = 50;

function progressLabel(job: EloquenceScoringJob): string {
  if (job.analysis_mode === "batch") {
    return job.status === "running"
      ? `Submitting ${job.total} post(s) as batch jobs…`
      : `Submitted ${job.submitted} post(s) across ${job.batch_jobs} batch job(s).`;
  }
  return `${job.processed} / ${job.total} scored · ${job.eloquent} eloquent · ${job.not_eloquent} not eloquent` +
    (job.failed > 0 ? ` · ${job.failed} failed` : "");
}

export default function EloquenceScoring() {
  const router = useRouter();
  const [force, setForce] = useState(false);
  const [candidates, setCandidates] = useState<EloquenceCandidatesResponse | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  // Starts true: the mount effect below fetches the first count.
  const [candidatesLoading, setCandidatesLoading] = useState(true);

  const [limitInput, setLimitInput] = useState(String(DEFAULT_LIMIT));
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [job, setJob] = useState<EloquenceScoringJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function loadCandidates(f: boolean) {
    setCandidatesLoading(true);
    setCandidatesError(null);
    try {
      const res = await fetch(`/api/eloquence-scoring/candidates?force=${f}`);
      const data: EloquenceCandidatesResponse & { error?: string } = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Could not count candidates.");
      setCandidates(data);
    } catch (err) {
      setCandidatesError(err instanceof Error ? err.message : "Could not count candidates.");
    } finally {
      setCandidatesLoading(false);
    }
  }

  // On mount: count candidates and recover a job that's still running (or
  // just finished) from before a page reload — the backend keeps the last
  // job in memory, so the readout survives navigating away and back.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/eloquence-scoring/candidates?force=false")
      .then(async (res) => {
        const data: EloquenceCandidatesResponse & { error?: string } = await res.json();
        if (cancelled) return;
        if (!res.ok) throw new Error(data.error ?? "Could not count candidates.");
        setCandidates(data);
      })
      .catch((err) => {
        if (!cancelled) setCandidatesError(err instanceof Error ? err.message : "Could not count candidates.");
      })
      .finally(() => {
        if (!cancelled) setCandidatesLoading(false);
      });
    fetch("/api/eloquence-scoring/status")
      .then(async (res) => {
        const data: { data?: EloquenceScoringJob | null } = await res.json();
        if (!cancelled && data.data) setJob(data.data);
      })
      .catch(() => {
        // Non-critical — the card still works for starting a new run.
      });
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  useEffect(() => {
    if (!job || job.status !== "running") {
      stopPolling();
      return;
    }
    if (pollRef.current !== null) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch("/api/eloquence-scoring/status");
        const data: { data?: EloquenceScoringJob | null } = await res.json();
        if (data.data) {
          setJob(data.data);
          if (data.data.status !== "running") {
            stopPolling();
            // Verdicts have landed: re-count what's left, and refresh so
            // the /eloquent feed's server-rendered data isn't stale.
            loadCandidates(force);
            router.refresh();
          }
        }
      } catch {
        // Transient poll failure — keep trying on the next tick.
      }
    }, POLL_INTERVAL_MS);
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [job?.log_tail]);

  async function handleForceChange(next: boolean) {
    setForce(next);
    await loadCandidates(next);
  }

  async function start(limit: number | null) {
    setStarting(true);
    setStartError(null);
    try {
      const res = await fetch("/api/eloquence-scoring", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit, force }),
      });
      const data: { data?: EloquenceScoringJob; error?: string } = await res.json();
      if (!res.ok || !data.data) throw new Error(data.error ?? "Could not start scoring.");
      setJob(data.data);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Could not start scoring.");
    } finally {
      setStarting(false);
    }
  }

  const candidateCount = candidates?.candidate_count ?? 0;
  const parsedLimit = Number.parseInt(limitInput, 10);
  const limitValid = Number.isInteger(parsedLimit) && parsedLimit >= 1;
  const running = job?.status === "running";
  const busy = starting || running || candidatesLoading;
  const canStart = !busy && candidateCount > 0;
  const progressPct =
    job && job.total > 0 ? Math.min(100, Math.round((job.processed / job.total) * 100)) : 0;

  return (
    <div className="mb-8 rounded-2xl border border-line bg-surface p-5">
      <h2 className="mb-1 text-sm font-bold text-ink-muted">Eloquence scoring</h2>
      <p className="text-ink-muted text-sm">
        Judge transcripts for oratory eloquence so they show up on the Eloquent page. Same criteria as
        <code className="mx-1 rounded bg-line/40 px-1 py-0.5 text-xs">scripts/score_eloquence.py</code>:
        transcript over {candidates?.length_threshold ?? 800} characters, not already scored, and a low
        filler-word ratio.
      </p>

      <div className="mt-4 rounded-xl border border-line px-4 py-3">
        {candidatesLoading && !candidates ? (
          <p className="text-sm text-ink-muted">Counting candidates…</p>
        ) : candidatesError ? (
          <p className="text-sm text-danger">{candidatesError}</p>
        ) : candidates ? (
          <>
            <p className="text-sm text-ink">
              <span className="font-display text-2xl font-semibold">{candidates.candidate_count}</span>{" "}
              post{candidates.candidate_count === 1 ? "" : "s"} pass the criteria
              {candidatesLoading && <span className="ml-2 text-xs text-ink-muted">(recounting…)</span>}
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {candidates.total_over_threshold} over the length threshold
              {force ? "" : " and unscored"}
              {candidates.skipped_prefilter > 0 && <> · {candidates.skipped_prefilter} dropped by the filler-ratio pre-filter</>}
              {candidates.skipped_pending > 0 && <> · {candidates.skipped_pending} already in a pending batch</>}
              {" · "}mode: {candidates.analysis_mode}
            </p>
          </>
        ) : null}
      </div>

      <label className="mt-4 flex items-start gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={force}
          disabled={busy}
          onChange={(e) => handleForceChange(e.target.checked)}
          className="mt-0.5 h-4 w-4 cursor-pointer accent-coral"
        />
        <span>
          Include posts that already have a verdict (re-score them) — for after a rubric change. Off by
          default so re-runs don&rsquo;t re-spend LLM calls on posts already judged.
        </span>
      </label>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-ink">
          Score the first
          <input
            type="number"
            min={1}
            max={Math.max(1, candidateCount)}
            value={limitInput}
            disabled={busy}
            onChange={(e) => setLimitInput(e.target.value)}
            className="w-24 rounded-full border border-line bg-surface px-3 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral disabled:opacity-50"
          />
        </label>
        <button
          onClick={() => start(Math.min(parsedLimit, candidateCount))}
          disabled={!canStart || !limitValid}
          className="rounded-full bg-coral px-5 py-2 text-sm font-bold text-white hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {starting ? "Starting…" : `Score ${limitValid ? Math.min(parsedLimit, candidateCount) : "…"}`}
        </button>
        <button
          onClick={() => start(null)}
          disabled={!canStart}
          className="rounded-full border border-line px-5 py-2 text-sm font-bold text-ink-muted hover:text-coral-ink hover:border-coral transition-colors disabled:opacity-50"
        >
          Score all {candidateCount}
        </button>
      </div>

      {startError && (
        <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
          {startError}
        </p>
      )}

      {job && (
        <div className="mt-5 rounded-xl border border-line px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-ink">{progressLabel(job)}</p>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${
                job.status === "running"
                  ? "bg-coral/15 text-coral-ink"
                  : job.status === "complete"
                    ? "bg-teal/15 text-teal-ink"
                    : "bg-danger-soft text-danger"
              }`}
            >
              {job.status}
            </span>
          </div>

          {job.analysis_mode !== "batch" && (
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-line">
              <div className="h-full bg-coral transition-[width]" style={{ width: `${progressPct}%` }} />
            </div>
          )}

          {job.analysis_mode === "batch" && job.status === "complete" && (
            <p className="mt-2 text-xs text-ink-muted">
              Verdicts arrive once OpenAI finishes the batch (minutes to 24h) — use &ldquo;Check batches&rdquo;
              above to pick them up.
            </p>
          )}

          {job.error && (
            <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
              {job.error}
            </p>
          )}

          <pre
            ref={logRef}
            className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-xl bg-ink/95 px-3 py-2 text-xs text-white/90"
          >
            {job.log_tail || "Waiting for output…"}
          </pre>
        </div>
      )}
    </div>
  );
}
