"use client";

import { useEffect, useRef, useState } from "react";
import CheckBatchesButton from "@/components/CheckBatchesButton";
import RefreshButton from "@/components/RefreshButton";
import StuckReels from "@/components/StuckReels";
import type { ImportJob, InstagramExportPreview } from "@/types/domain";

const POLL_INTERVAL_MS = 3000;
const DEFAULT_PRIORITY_FOLDER = "Important";

function formatStarted(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function AdminPage() {
  const [file, setFile] = useState<File | null>(null);
  const [allPostsFile, setAllPostsFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<InstagramExportPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [mode, setMode] = useState<"regular" | "by_collection">("regular");
  const [priorityFolder, setPriorityFolder] = useState(DEFAULT_PRIORITY_FOLDER);
  // Off by default — real save dates now come from the all-posts file
  // regardless of analysis order, so this is just a processing-order
  // preference. See scripts/import_saved_instagram.py's
  // --reverse-collections docstring.
  const [reverseCollections, setReverseCollections] = useState(false);

  const [startError, setStartError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [activeJob, setActiveJob] = useState<ImportJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<ImportJob[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function applyRecentJobs(jobs: ImportJob[], recoverActive: boolean) {
    setRecentJobs(jobs);
    // Recover an in-progress run after a page reload — resume watching it
    // instead of leaving the page with no visible status.
    if (recoverActive) {
      const running = jobs.find((j) => j.status === "running");
      if (running) setActiveJob(running);
    }
  }

  async function loadRecentJobs() {
    try {
      const res = await fetch("/api/instagram-export/jobs");
      const data: { data?: ImportJob[] } = await res.json();
      applyRecentJobs(data.data ?? [], false);
    } catch {
      // Non-critical — the page still works for starting a new import.
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetch("/api/instagram-export/jobs")
      .then(async (res) => {
        const data: { data?: ImportJob[] } = await res.json();
        if (cancelled) return;
        applyRecentJobs(data.data ?? [], true);
      })
      .catch(() => {
        // Non-critical — the page still works for starting a new import.
      });
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  useEffect(() => {
    if (!activeJob || activeJob.status !== "running") {
      stopPolling();
      return;
    }
    if (pollRef.current !== null) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/instagram-export/jobs/${activeJob.id}`);
        const data: { data?: ImportJob } = await res.json();
        if (data.data) {
          setActiveJob(data.data);
          if (data.data.status !== "running") {
            stopPolling();
            loadRecentJobs();
          }
        }
      } catch {
        // Transient poll failure — keep trying on the next tick.
      }
    }, POLL_INTERVAL_MS);
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJob?.id, activeJob?.status]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [activeJob?.log_tail]);

  async function runPreview(f: File | null, apf: File | null) {
    setPreview(null);
    setPreviewError(null);
    setStartError(null);
    if (!f) return;

    setPreviewLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", f);
      if (apf) formData.append("allPostsFile", apf);
      const res = await fetch("/api/instagram-export/preview", { method: "POST", body: formData });
      const data: InstagramExportPreview & { error?: string } = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Could not parse that file.");
      setPreview(data);
      const hasDefault = data.categories.some((c) => c.name === DEFAULT_PRIORITY_FOLDER);
      setPriorityFolder(hasDefault ? DEFAULT_PRIORITY_FOLDER : (data.categories[0]?.name ?? ""));
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Could not parse that file.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    await runPreview(f, allPostsFile);
  }

  async function handleAllPostsFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const apf = e.target.files?.[0] ?? null;
    setAllPostsFile(apf);
    // Re-run the preview so the "known save date" count reflects the newly
    // picked file — only meaningful once a collections file is already set.
    if (file) await runPreview(file, apf);
  }

  async function handleStart() {
    if (!file) return;
    setStarting(true);
    setStartError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (allPostsFile) formData.append("allPostsFile", allPostsFile);
      formData.append("mode", mode);
      if (mode === "by_collection") formData.append("priorityFolder", priorityFolder);
      formData.append("reverseCollections", String(reverseCollections));

      const res = await fetch("/api/instagram-export/jobs", { method: "POST", body: formData });
      const data: { data?: ImportJob; error?: string } = await res.json();
      if (!res.ok || !data.data) throw new Error(data.error ?? "Could not start the import.");
      setActiveJob(data.data);
      loadRecentJobs();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Could not start the import.");
    } finally {
      setStarting(false);
    }
  }

  const selectClass =
    "rounded-full border border-line bg-surface px-4 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-coral cursor-pointer";

  return (
    <div className="mx-auto max-w-3xl px-5 py-8">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-3xl">Admin</h1>
        <p className="mt-1 text-ink-muted text-sm">
          Import new content and manage background analysis jobs.
        </p>
      </div>

      <div className="mb-8 rounded-2xl border border-line bg-surface p-5">
        <h2 className="mb-3 text-sm font-bold text-ink-muted">Analysis jobs</h2>
        <div className="flex flex-wrap items-center gap-3">
          <RefreshButton />
          <CheckBatchesButton />
        </div>
      </div>

      <StuckReels />

      <div className="mb-6">
        <h2 className="text-sm font-bold text-ink-muted">Import</h2>
        <p className="mt-1 text-ink-muted text-sm">
          Upload an Instagram &ldquo;Download Your Information&rdquo; export and analyze the reels/posts it contains.
        </p>
      </div>

      {activeJob ? (
        <div className="rounded-2xl border border-line bg-surface p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-bold text-ink">
                {activeJob.mode === "by_collection" ? "By category" : "Regular"} import
                {activeJob.priority_folder ? ` (priority: ${activeJob.priority_folder})` : ""}
              </p>
              <p className="text-xs text-ink-muted">Started {formatStarted(activeJob.started_at)}</p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${
                activeJob.status === "running"
                  ? "bg-coral/15 text-coral-ink"
                  : activeJob.status === "complete"
                    ? "bg-teal/15 text-teal-ink"
                    : "bg-danger-soft text-danger"
              }`}
            >
              {activeJob.status}
            </span>
          </div>

          {activeJob.error && (
            <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
              {activeJob.error}
            </p>
          )}

          <pre
            ref={logRef}
            className="mt-4 h-72 overflow-y-auto whitespace-pre-wrap rounded-xl bg-ink/95 px-3 py-2 text-xs text-white/90"
          >
            {activeJob.log_tail || "Waiting for output…"}
          </pre>

          {activeJob.status !== "running" && (
            <button
              onClick={() => {
                setActiveJob(null);
                setFile(null);
                setAllPostsFile(null);
                setPreview(null);
              }}
              className="mt-4 rounded-full border border-line px-4 py-2 text-sm font-bold text-ink-muted hover:text-coral-ink hover:border-coral transition-colors"
            >
              Start another import
            </button>
          )}
        </div>
      ) : (
        <div className="rounded-2xl border border-line bg-surface p-5">
          <label className="block cursor-pointer rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted hover:border-coral hover:text-coral-ink transition-colors">
            <input type="file" accept=".json" className="hidden" onChange={handleFileChange} />
            {file ? file.name : "Choose a “by collection” export JSON file"}
          </label>

          <label className="mt-3 block cursor-pointer rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted hover:border-coral hover:text-coral-ink transition-colors">
            <input type="file" accept=".json" className="hidden" onChange={handleAllPostsFileChange} />
            {allPostsFile ? allPostsFile.name : "Choose an all-posts export JSON file (optional, for save dates)"}
          </label>

          {previewLoading && <p className="mt-3 text-sm text-ink-muted">Parsing…</p>}
          {previewError && (
            <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
              {previewError}
            </p>
          )}

          {preview && (
            <>
              <div className="mt-4 max-h-48 overflow-y-auto rounded-xl border border-line">
                <table className="w-full text-sm">
                  <tbody>
                    {preview.categories.map((c) => (
                      <tr key={c.name} className="border-b border-line last:border-0">
                        <td className="px-3 py-1.5 text-ink">{c.name}</td>
                        <td className="px-3 py-1.5 text-right text-ink-muted">{c.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-ink-muted">
                {preview.total_unique_posts} unique post(s) across {preview.categories.length} categor
                {preview.categories.length === 1 ? "y" : "ies"} ({preview.total_raw_entries} raw entries).
                {preview.posts_with_known_date != null && (
                  <> {preview.posts_with_known_date} of them have a known save date.</>
                )}
              </p>

              <div className="mt-5 flex flex-wrap items-center gap-3">
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value === "by_collection" ? "by_collection" : "regular")}
                  className={selectClass}
                >
                  <option value="regular">Regular order</option>
                  <option value="by_collection">By category (priority first)</option>
                </select>

                {mode === "by_collection" && (
                  <select
                    value={priorityFolder}
                    onChange={(e) => setPriorityFolder(e.target.value)}
                    className={selectClass}
                  >
                    {preview.categories.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <label className="mt-4 flex items-start gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={reverseCollections}
                  onChange={(e) => setReverseCollections(e.target.checked)}
                  className="mt-0.5 h-4 w-4 cursor-pointer accent-coral"
                />
                <span>
                  Reverse each category — Instagram lists each collection newest-saved-first; this analyzes
                  oldest-first instead. Off by default: real save dates now come from the all-posts file
                  regardless of analysis order, so this is just a processing-order preference, not required
                  for date accuracy.
                </span>
              </label>

              {startError && (
                <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
                  {startError}
                </p>
              )}

              <button
                onClick={handleStart}
                disabled={starting}
                className="mt-4 rounded-full bg-coral px-5 py-2 text-sm font-bold text-white hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {starting ? "Starting…" : "Start import"}
              </button>
            </>
          )}
        </div>
      )}

      {recentJobs.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-bold text-ink-muted">Recent imports</h2>
          <div className="divide-y divide-line rounded-2xl border border-line bg-surface">
            {recentJobs.map((job) => (
              <button
                key={job.id}
                onClick={() => setActiveJob(job)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-line/20 transition-colors"
              >
                <span className="text-ink">
                  {job.mode === "by_collection" ? "By category" : "Regular"} · {formatStarted(job.started_at)}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                    job.status === "running"
                      ? "bg-coral/15 text-coral-ink"
                      : job.status === "complete"
                        ? "bg-teal/15 text-teal-ink"
                        : "bg-danger-soft text-danger"
                  }`}
                >
                  {job.status}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
