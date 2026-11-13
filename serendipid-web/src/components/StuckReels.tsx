"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import type {
  AttentionItem,
  ManualUploadResult,
  QueueAttentionResponse,
  RetryDownloadResult,
  RetryFlushResponse,
} from "@/types/domain";

// Triage table for reels that stopped making progress, plus the two ways out.
// Two backing sources are reconciled server-side (see backend/api.py's
// queue_attention()); this component presents the result as one scannable row
// per reel — shortcode, its Instagram link, what state it's in, a button to
// make the backend try the download again, and a drop target for handing over
// the video yourself when Instagram won't serve it.
//
// A reel that actually gets analyzed disappears from the table immediately
// rather than waiting for a refresh: it now has a row in `analyses`, so the
// next fetch would drop it anyway, and leaving it on screen invites a second
// pointless (and paid) analysis of the same post.

const ROWS_BEFORE_TRUNCATION = 60;
const TOAST_AUTO_DISMISS_MS = 9000;

// Backend timestamps come in two flavours: processing_queue rows are
// `datetime.utcnow().isoformat()` (no zone designator — JS would otherwise
// read them as local time and be hours off), while the import state file
// writes real tz-aware ISO strings. Normalize before parsing.
function parseBackendDate(iso: string | null): Date | null {
  if (!iso) return null;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatWhen(iso: string | null): string {
  const d = parseBackendDate(iso);
  return d ? d.toLocaleString() : "—";
}

function formatRelativeToNow(iso: string | null): string | null {
  const d = parseBackendDate(iso);
  if (!d) return null;
  const diffMs = d.getTime() - Date.now();
  if (diffMs <= 0) return "due now";
  const hours = Math.floor(diffMs / 3_600_000);
  const minutes = Math.round((diffMs % 3_600_000) / 60_000);
  if (hours >= 1) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

// Strip the scheme and trailing slash so the URL column stays scannable —
// every one of these is instagram.com, so those characters carry no signal.
function shortenUrl(url: string): string {
  return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}

const STATE_LABELS: Record<AttentionItem["state"], string> = {
  processing: "analyzing now",
  queued: "queued",
  batch: "in an AI batch",
  retry: "auto-retry",
  import_pending: "not reached yet",
  abandoned: "gave up",
};

const STATE_STYLES: Record<AttentionItem["state"], string> = {
  processing: "bg-teal/15 text-teal-ink",
  queued: "bg-sky-soft text-sky-ink",
  batch: "bg-lavender-soft text-lavender-ink",
  retry: "bg-yellow-soft text-yellow-ink",
  import_pending: "bg-line/40 text-ink-muted",
  abandoned: "bg-danger-soft text-danger",
};

type ToastTone = "success" | "warn" | "info";

interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  message: string;
  // Present only when a manual upload is the sensible next step — the toast
  // opens that row's own file picker, so the decision and the action are in
  // the same place.
  offerUploadFor?: AttentionItem;
  href?: { label: string; url: string };
}

const TOAST_TONES: Record<ToastTone, string> = {
  success: "border-teal/40 bg-teal/10 text-teal-ink",
  warn: "border-danger/30 bg-danger-soft text-coral-ink",
  info: "border-line bg-surface-2 text-ink",
};

export default function StuckReels() {
  const [data, setData] = useState<QueueAttentionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [tab, setTab] = useState<"pending" | "abandoned">("pending");
  const [includeAnalyzed, setIncludeAnalyzed] = useState(false);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [filter, setFilter] = useState("");
  // null = every state. The row cap plus the last-touched ordering means a
  // state that clusters at one end of the list (batch rows, say) can be
  // almost entirely below the fold; this is how you isolate one instead of
  // hunting for it.
  const [stateFilter, setStateFilter] = useState<AttentionItem["state"] | null>(null);
  const [showAll, setShowAll] = useState(false);

  // Reels the backend has taken ownership of during this session — analyzed,
  // submitted to an AI batch, or queued. Hidden from the table immediately so
  // the same reel can't be actioned twice.
  //
  // This is not cosmetic. A re-click on a reel that's already in flight is
  // NOT the harmless cache hit it looks like: /analyze only guards
  // status='processing' (409) and de-dupes status='queued', so a reel sitting
  // at status='batch' would be marked processing again and re-downloaded and
  // re-analyzed from scratch — paying for the work twice and orphaning its
  // batch_jobs row.
  const [handedOff, setHandedOff] = useState<Set<string>>(new Set());
  const [showHandedOff, setShowHandedOff] = useState(false);
  // Only one action may run at a time: the backend analyzes one post at a
  // time (max_concurrent is 1), so parallel attempts would just queue behind
  // each other while looking like independent work.
  const [busy, setBusy] = useState<{ shortcode: string; kind: "download" | "upload" } | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [confirmingFlush, setConfirmingFlush] = useState(false);
  const [flushing, setFlushing] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const dismissToast = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const pushToast = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = ++toastId.current;
      setToasts((t) => [...t, { ...toast, id }]);
      // Anything that needs a decision stays until it's acted on or dismissed;
      // pure status reports clear themselves.
      if (!toast.offerUploadFor) {
        setTimeout(() => dismissToast(id), TOAST_AUTO_DISMISS_MS);
      }
    },
    [dismissToast]
  );

  const attentionUrl = `/api/queue-attention?includeAnalyzed=${includeAnalyzed}&includeDeleted=${includeDeleted}`;

  // Manual refresh. An event handler, so setting state synchronously is fine
  // here — unlike the effect below.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(attentionUrl);
      const body: QueueAttentionResponse & { error?: string } = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Could not load the queue.");
      setData(body);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the queue.");
    } finally {
      setLoading(false);
    }
  }, [attentionUrl]);

  // Initial load, and a reload whenever the include-filters change. Written
  // with promise callbacks rather than as `useEffect(() => { load() })`: the
  // react-hooks/set-state-in-effect rule treats any call from an effect body
  // into a function that sets state as a synchronous setState, so awaiting
  // inside load() isn't enough to satisfy it. Same shape as AdminPage's own
  // initial fetch, where state is only touched from a .then callback.
  useEffect(() => {
    let cancelled = false;
    fetch(attentionUrl)
      .then(async (res) => ({ ok: res.ok, body: await res.json() }))
      .then(({ ok, body }: { ok: boolean; body: QueueAttentionResponse & { error?: string } }) => {
        if (cancelled) return;
        if (!ok) throw new Error(body.error ?? "Could not load the queue.");
        setData(body);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load the queue.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attentionUrl]);

  const buckets = useMemo(() => {
    const keep = (list: AttentionItem[]) =>
      showHandedOff ? list : list.filter((i) => !handedOff.has(i.shortcode));
    return {
      pending: keep(data?.pending ?? []),
      abandoned: keep(data?.abandoned ?? []),
    };
  }, [data, handedOff, showHandedOff]);

  // Counts are of the whole tab, before the state/text filters, so a chip
  // always shows how many exist rather than how many survive the current
  // filter (which would make every unselected chip read 0).
  const stateCounts = useMemo(() => {
    const counts = new Map<AttentionItem["state"], number>();
    for (const i of buckets[tab]) counts.set(i.state, (counts.get(i.state) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [buckets, tab]);

  const items = useMemo(() => {
    const byState = stateFilter
      ? buckets[tab].filter((i) => i.state === stateFilter)
      : buckets[tab];
    const source = byState;
    const needle = filter.trim().toLowerCase();
    if (!needle) return source;
    return source.filter(
      (i) =>
        i.shortcode.toLowerCase().includes(needle) ||
        i.url.toLowerCase().includes(needle) ||
        i.folders.some((f) => f.toLowerCase().includes(needle)) ||
        (i.last_error ?? "").toLowerCase().includes(needle) ||
        (i.reason ?? "").toLowerCase().includes(needle)
    );
  }, [buckets, tab, filter, stateFilter]);

  const visible = showAll ? items : items.slice(0, ROWS_BEFORE_TRUNCATION);

  // Deliberately counted off the raw payload, not `buckets`/`items`: the
  // flush is a backend-wide operation on every status='retry' row, so the
  // button must not promise a number that the current tab or filters happen
  // to be showing.
  const retryWaitingCount = (data?.pending ?? []).filter((i) => i.state === "retry").length;

  // Call for any outcome that means "the backend now owns this reel" —
  // analyzed, submitted to a batch, or queued. An analyzed reel would also
  // drop out on the next fetch (it has an `analyses` row, which
  // /queue/attention filters on), but the in-flight ones would not: they're
  // still legitimately pending server-side, and only this session knows they
  // were just actioned.
  function markHandedOff(shortcode: string) {
    setHandedOff((s) => new Set(s).add(shortcode));
  }

  // The toast's shortcut reuses the row's own hidden file input, which only
  // exists while that row is on screen — a filter or tab change between the
  // toast appearing and being acted on would otherwise make the button a
  // silent no-op.
  function openUploadFor(toast: Toast) {
    const input = fileInputs.current[toast.offerUploadFor!.shortcode];
    if (!input) {
      pushToast({
        tone: "info",
        title: "That row isn't on screen any more",
        message: "Clear the filter or switch tabs, then use that row's own upload cell.",
      });
      return;
    }
    input.click();
    dismissToast(toast.id);
  }

  // Promotes every status='retry' reel back into the active queue, ignoring
  // the 24h wait each one is sitting out. Behind a confirm because it is
  // rarely the shortcut it looks like — see the toast copy and the backend
  // route's docstring.
  async function flushRetries() {
    setFlushing(true);
    try {
      const res = await fetch("/api/queue-retry-flush?force=true", { method: "POST" });
      const body: RetryFlushResponse & { error?: string } = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Could not flush the retry queue.");
      pushToast({
        tone: body.flushed > 0 ? "success" : "info",
        title:
          body.flushed > 0
            ? `${body.flushed} reel(s) re-queued`
            : "Nothing was waiting on a retry",
        message:
          body.flushed > 0
            ? "They're back in the active queue. The backend analyzes one at a time, so this drains gradually — and any that Instagram is still blocking will simply be re-queued for another wait."
            : "The retry queue is empty right now.",
      });
    } catch (err) {
      pushToast({
        tone: "warn",
        title: "Could not flush the retry queue",
        message: err instanceof Error ? err.message : "The request failed.",
      });
    } finally {
      setFlushing(false);
      setConfirmingFlush(false);
      void load();
    }
  }

  async function tryDownload(item: AttentionItem) {
    setBusy({ shortcode: item.shortcode, kind: "download" });
    try {
      const res = await fetch("/api/retry-download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: item.url }),
      });
      const body: RetryDownloadResult & { error?: string } = await res.json();
      if (!res.ok) throw new Error(body.error ?? "The download attempt failed.");

      switch (body.outcome) {
        case "analyzed":
          markHandedOff(item.shortcode);
          pushToast({
            tone: "success",
            title: `${item.shortcode} — downloaded and analyzed`,
            message: body.title ? `“${body.title}”` : "The reel is saved.",
            href: { label: "Open the post", url: `/post/${item.shortcode}` },
          });
          break;
        case "batch_submitted":
          // ANALYSIS_MODE=batch: the download WORKED and the analysis is in
          // an OpenAI batch. Same 202 as a blocked download, opposite
          // meaning — nothing is wrong and nothing needs uploading. Hidden
          // like an analyzed reel even though there's no `analyses` row yet:
          // retrying one of these re-downloads and re-analyzes it from
          // scratch (see markHandedOff), which is the opposite of harmless.
          markHandedOff(item.shortcode);
          pushToast({
            tone: "success",
            title: `${item.shortcode} — downloaded, analysis submitted to a batch`,
            message: `${body.detail} Removed from the table so it can't be retried while it's in flight.`,
          });
          break;
        case "retry_scheduled":
          pushToast({
            tone: "warn",
            title: `${item.shortcode} — Instagram blocked the download`,
            message: `${body.detail} Its normal auto-retry is untouched, so it'll try again on its own — or you can get the video yourself now.`,
            offerUploadFor: item,
          });
          break;
        case "queued":
          markHandedOff(item.shortcode);
          pushToast({
            tone: "info",
            title: `${item.shortcode} — backend busy`,
            message: `${body.detail} Nothing to decide: it's in the queue and will be analyzed automatically.`,
          });
          break;
        case "already_in_flight":
          // The backend refused to duplicate work it's already doing. Not a
          // failure, and a manual upload wouldn't help — it would hit the
          // same guard.
          markHandedOff(item.shortcode);
          pushToast({
            tone: "info",
            title: `${item.shortcode} — already being worked on`,
            message: `${body.detail}`,
          });
          break;
        case "timeout":
          pushToast({
            tone: "info",
            title: `${item.shortcode} — still running`,
            message:
              "The backend didn't answer in time, but it's probably still working. Refresh in a few minutes before trying again.",
          });
          break;
        default:
          pushToast({
            tone: "warn",
            title: `${item.shortcode} — download failed`,
            message: `${body.detail} Uploading the video yourself skips the download entirely.`,
            offerUploadFor: item,
          });
      }
    } catch (err) {
      pushToast({
        tone: "warn",
        title: `${item.shortcode} — download failed`,
        message: err instanceof Error ? err.message : "The download attempt failed.",
        offerUploadFor: item,
      });
    } finally {
      setBusy(null);
      // Re-read from the backend so the rest of the table reflects whatever
      // that attempt changed server-side — a reel that just got analyzed
      // drops out on its own (it has an `analyses` row now), counts move,
      // and a row whose state advanced stops advertising a stale one.
      void load();
    }
  }

  async function handleFile(item: AttentionItem, file: File) {
    setBusy({ shortcode: item.shortcode, kind: "upload" });
    try {
      const form = new FormData();
      form.append("url", item.url);
      form.append("file", file, file.name);
      const res = await fetch("/api/manual-upload", { method: "POST", body: form });
      const body: ManualUploadResult & { error?: string } = await res.json();
      if (!res.ok) throw new Error(body.error ?? "The upload failed.");

      switch (body.outcome) {
        case "analyzed":
          markHandedOff(item.shortcode);
          pushToast({
            tone: "success",
            title: `${item.shortcode} — analyzed from your file`,
            message: body.title ? `“${body.title}”` : "The reel is saved.",
            href: { label: "Open the post", url: `/post/${item.shortcode}` },
          });
          break;
        case "queued":
          // The file is already on the backend and pinned to the queue row
          // (processing_queue.media_folder), so this is a success — but the
          // reel isn't analyzed yet, so the row stays.
          markHandedOff(item.shortcode);
          pushToast({
            tone: "info",
            title: `${item.shortcode} — uploaded, waiting its turn`,
            message:
              "The backend analyzes one post at a time and is busy. Your file is saved and will be used instead of a download — no need to upload it again.",
          });
          break;
        case "batch_submitted":
          // ANALYSIS_MODE=batch — your file was accepted and analyzed up to
          // the point where the AI calls go to OpenAI's Batch API. Working,
          // not blocked; it just lands within 24h rather than now.
          markHandedOff(item.shortcode);
          pushToast({
            tone: "success",
            title: `${item.shortcode} — your file was accepted, analysis submitted to a batch`,
            message: `${body.detail} No need to upload it again.`,
          });
          break;
        case "timeout":
          pushToast({
            tone: "info",
            title: `${item.shortcode} — still analyzing`,
            message:
              "The backend is still working on your file — the connection timed out before it answered. Check the post in a few minutes before uploading again.",
          });
          break;
        default:
          // retry_scheduled: the upload was consumed but a later step (audio
          // transcription) failed, so the backend queued a retry it can no
          // longer serve — the media was moved out of the upload folder.
          pushToast({
            tone: "warn",
            title: `${item.shortcode} — upload accepted, but analysis stalled`,
            message: `${body.detail} You'll need to upload the file again once that clears.`,
          });
      }
    } catch (err) {
      pushToast({
        tone: "warn",
        title: `${item.shortcode} — upload failed`,
        message: err instanceof Error ? err.message : "The upload failed.",
      });
    } finally {
      setBusy(null);
      setDragOver(null);
      void load();
    }
  }

  const headCell = "px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-ink-muted";

  return (
    <div className="mb-8 rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-ink-muted">Stuck reels</h2>
          <p className="mt-1 max-w-xl text-xs text-ink-muted">
            Reels that never finished analyzing. Retry the backend&rsquo;s own downloader, or drop in
            the video yourself when Instagram won&rsquo;t serve it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {retryWaitingCount > 0 && (
            <button
              onClick={() => setConfirmingFlush(true)}
              disabled={flushing || busy !== null}
              className="rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:border-coral hover:text-coral-ink transition-colors disabled:opacity-50"
            >
              {flushing ? "Re-queuing…" : `⏩ Retry all ${retryWaitingCount} now`}
            </button>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:border-coral hover:text-coral-ink transition-colors disabled:opacity-50"
          >
            {loading ? "Loading…" : "↻ Refresh"}
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {(["pending", "abandoned"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setStateFilter(null);
              setShowAll(false);
            }}
            className={`rounded-full px-4 py-1.5 text-xs font-bold transition-colors ${
              tab === t
                ? "bg-coral text-white"
                : "border border-line text-ink-muted hover:border-coral hover:text-coral-ink"
            }`}
          >
            {t === "pending" ? "Pending" : "Not being retried"} ({buckets[t].length})
          </button>
        ))}

        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Narrow the table…"
          className="ml-auto w-52 rounded-full border border-line bg-surface px-4 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-coral"
        />
      </div>

      {stateCounts.length > 1 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => {
              setStateFilter(null);
              setShowAll(false);
            }}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
              stateFilter === null
                ? "bg-ink text-bg"
                : "border border-line text-ink-muted hover:border-coral hover:text-coral-ink"
            }`}
          >
            All ({buckets[tab].length})
          </button>
          {stateCounts.map(([state, count]) => (
            <button
              key={state}
              onClick={() => {
                setStateFilter((cur) => (cur === state ? null : state));
                setShowAll(false);
              }}
              className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
                stateFilter === state
                  ? `${STATE_STYLES[state]} ring-2 ring-coral`
                  : `${STATE_STYLES[state]} opacity-70 hover:opacity-100`
              }`}
            >
              {STATE_LABELS[state]} ({count})
            </button>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-4 text-xs text-ink-muted">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={includeAnalyzed}
            onChange={(e) => setIncludeAnalyzed(e.target.checked)}
            className="h-3.5 w-3.5 cursor-pointer accent-coral"
          />
          Show already analyzed
          {data && data.hidden_analyzed > 0 && !includeAnalyzed ? ` (${data.hidden_analyzed})` : ""}
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={includeDeleted}
            onChange={(e) => setIncludeDeleted(e.target.checked)}
            className="h-3.5 w-3.5 cursor-pointer accent-coral"
          />
          Show deleted posts
          {data && data.hidden_deleted > 0 && !includeDeleted ? ` (${data.hidden_deleted})` : ""}
        </label>
      </div>

      {handedOff.size > 0 && (
        <p className="mt-3 text-xs text-ink-muted">
          {handedOff.size} reel(s) handed to the backend this session{" "}
          {showHandedOff ? "are shown below" : "are hidden"} so they can&rsquo;t be actioned twice.{" "}
          <button
            onClick={() => setShowHandedOff((v) => !v)}
            className="font-bold underline hover:text-coral-ink transition-colors"
          >
            {showHandedOff ? "Hide them" : "Show them anyway"}
          </button>
        </p>
      )}

      {error && (
        <p className="mt-4 rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-coral-ink">
          {error}
        </p>
      )}

      {!error && !loading && visible.length === 0 && (
        <p className="mt-5 rounded-xl border border-dashed border-line px-4 py-6 text-center text-xs text-ink-muted">
          {tab === "abandoned"
            ? "Nothing has been given up on — every unfinished reel is still scheduled to retry."
            : "Nothing is waiting to be analyzed."}
        </p>
      )}

      {visible.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[880px] border-collapse text-sm">
            <thead className="bg-surface-2">
              <tr className="border-b border-line">
                <th className={headCell}>Shortcode</th>
                <th className={headCell}>Instagram URL</th>
                <th className={headCell}>Status</th>
                <th className={headCell}>Retry download</th>
                <th className={headCell}>Upload media</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visible.map((item) => {
                const retryIn = formatRelativeToNow(item.retry_after);
                const isBusy = busy?.shortcode === item.shortcode;
                const blocked = busy !== null && !isBusy;
                const uploading = isBusy && busy?.kind === "upload";
                // `reason`/`retry_after` describe a *scheduled retry*, and
                // queue_for_retry() never clears them when the row later moves
                // on. A reel that has since been picked up and submitted to an
                // AI batch still carries "instagram_rate_limit" from whenever
                // it last failed — showing that next to "in an AI batch" reads
                // as a live problem when nothing is wrong.
                const showsRetryInfo = item.state === "retry" || item.state === "abandoned";
                // Visible only via "Show them anyway", which is for checking
                // what happened — not for actioning it a second time, which
                // is the exact thing hiding these prevents.
                const isHandedOff = handedOff.has(item.shortcode);
                // The backend refuses both actions for these (409) — it's
                // already downloading this reel or has its analysis in an AI
                // batch. Better to show the button as unavailable than to
                // let the click happen and explain it afterwards.
                const inFlight = item.state === "batch" || item.state === "processing";
                const locked = isBusy || blocked || isHandedOff || inFlight;
                const isDragTarget = dragOver === item.shortcode;

                return (
                  <tr key={item.shortcode} className="align-top hover:bg-line/10 transition-colors">
                    <td className="px-3 py-2.5">
                      <code className="font-mono text-xs font-bold text-ink">{item.shortcode}</code>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {isHandedOff && (
                          <span className="rounded-full bg-teal/15 px-1.5 py-0.5 text-[10px] font-bold text-teal-ink">
                            handed off
                          </span>
                        )}
                        {item.analyzed && (
                          <span className="rounded-full bg-teal/15 px-1.5 py-0.5 text-[10px] font-bold text-teal-ink">
                            analyzed
                          </span>
                        )}
                        {item.deleted && (
                          <span className="rounded-full bg-line/40 px-1.5 py-0.5 text-[10px] font-bold text-ink-muted">
                            deleted
                          </span>
                        )}
                        {item.folders.map((f) => (
                          <span
                            key={f}
                            className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-muted"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    </td>

                    <td className="px-3 py-2.5">
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={item.url}
                        className="font-mono text-xs text-ink-muted underline decoration-line hover:text-coral-ink hover:decoration-coral transition-colors"
                      >
                        {shortenUrl(item.url)} ↗
                      </a>
                      <p className="mt-1 text-[10px] text-ink-muted">
                        Last touched {formatWhen(item.last_updated)}
                      </p>
                    </td>

                    <td className="px-3 py-2.5" title={item.last_error ?? undefined}>
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold ${STATE_STYLES[item.state]}`}
                      >
                        {STATE_LABELS[item.state]}
                      </span>
                      <p className="mt-1 text-[10px] text-ink-muted">
                        {showsRetryInfo && retryIn && <span className="block">retries in {retryIn}</span>}
                        {showsRetryInfo && item.reason && <span className="block">{item.reason}</span>}
                        {item.attempts > 0 && <span className="block">{item.attempts} attempt(s)</span>}
                      </p>
                    </td>

                    <td className="px-3 py-2.5">
                      <button
                        onClick={() => tryDownload(item)}
                        disabled={locked}
                        title={
                          inFlight
                            ? "The backend is already working on this reel — it refuses to duplicate the work."
                            : undefined
                        }
                        className="whitespace-nowrap rounded-full border border-line px-3 py-1.5 text-[11px] font-bold text-ink-muted hover:border-coral hover:text-coral-ink transition-colors disabled:opacity-40"
                      >
                        {isBusy && busy?.kind === "download"
                          ? "Trying…"
                          : inFlight
                            ? "in flight"
                            : "↻ Retry download"}
                      </button>
                    </td>

                    <td className="px-3 py-2.5">
                      <label
                        onDragOver={(e) => {
                          e.preventDefault();
                          if (!locked) setDragOver(item.shortcode);
                        }}
                        onDragLeave={() => setDragOver((s) => (s === item.shortcode ? null : s))}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOver(null);
                          if (locked) return;
                          const f = e.dataTransfer.files?.[0];
                          if (f) handleFile(item, f);
                        }}
                        className={`block cursor-pointer whitespace-nowrap rounded-lg border border-dashed px-3 py-1.5 text-center text-[11px] font-bold transition-colors ${
                          isDragTarget
                            ? "border-coral bg-coral/10 text-coral-ink"
                            : "border-line text-ink-muted hover:border-coral hover:text-coral-ink"
                        } ${locked ? "pointer-events-none opacity-40" : ""}`}
                      >
                        <input
                          ref={(el) => {
                            fileInputs.current[item.shortcode] = el;
                          }}
                          type="file"
                          accept="video/*,image/*"
                          className="hidden"
                          disabled={locked}
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            // Reset so re-picking the same file after a
                            // failure still fires a change event.
                            e.target.value = "";
                            if (f) handleFile(item, f);
                          }}
                        />
                        {uploading ? "Analyzing…" : inFlight ? "—" : "⬆ Drop or browse"}
                      </label>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {items.length > visible.length && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-3 rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:border-coral hover:text-coral-ink transition-colors"
        >
          Show all {items.length}
        </button>
      )}

      {busy && (
        <p className="mt-3 rounded-xl bg-surface-2 px-3 py-2 text-[11px] text-ink-muted">
          <code className="font-mono">{busy.shortcode}</code>:{" "}
          {busy.kind === "upload"
            ? "uploading and running the full analysis — visual, transcription, music, summary."
            : "asking the backend to download and analyze this now."}{" "}
          This usually takes a few minutes; leave this tab open. Other rows are disabled meanwhile —
          the backend only analyzes one post at a time.
        </p>
      )}

      {confirmingFlush && (
        <ConfirmDialog
          title={`Retry all ${retryWaitingCount} reels now?`}
          message={
            "These are waiting out a scheduled 24h retry, almost always because Instagram rate-limited the download — and that block clears with time, not with retrying. Flushing early mostly re-runs the same failures and re-queues them for another wait, and hammering a live block can extend it. " +
            "It costs no AI spend (a failed download never reaches the providers) and the backend analyzes one reel at a time, so it drains gradually rather than in a burst."
          }
          confirmLabel={flushing ? "Re-queuing…" : "Retry all now"}
          busy={flushing}
          onConfirm={flushRetries}
          onCancel={() => setConfirmingFlush(false)}
        />
      )}

      {toasts.length > 0 && (
        <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              role="status"
              className={`pointer-events-auto rounded-xl border px-4 py-3 shadow-lg ${TOAST_TONES[toast.tone]}`}
            >
              <p className="text-xs font-bold">{toast.title}</p>
              <p className="mt-1 text-[11px] opacity-90">{toast.message}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {toast.offerUploadFor && (
                  <button
                    onClick={() => openUploadFor(toast)}
                    className="rounded-full bg-coral px-3 py-1 text-[11px] font-bold text-white hover:opacity-90 transition-opacity"
                  >
                    ⬆ Upload it myself
                  </button>
                )}
                {toast.href && (
                  <a
                    href={toast.href.url}
                    className="rounded-full border border-current/30 px-3 py-1 text-[11px] font-bold hover:opacity-80 transition-opacity"
                  >
                    {toast.href.label}
                  </a>
                )}
                <button
                  onClick={() => dismissToast(toast.id)}
                  className="ml-auto text-[11px] font-bold opacity-70 hover:opacity-100"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
