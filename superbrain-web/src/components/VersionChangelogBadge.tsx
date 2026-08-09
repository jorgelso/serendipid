"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useChangelog } from "@/lib/useChangelog";

interface VersionChangelogModalProps {
  analysisVersion: number;
  onClose: () => void;
}

// Same portal/escape/scroll-lock/backdrop-click pattern as PostModal.tsx —
// PostCard's hover transform makes an ancestor-relative `fixed` modal
// mis-position itself, see that file's comment for the full explanation.
function VersionChangelogModal({ analysisVersion, onClose }: VersionChangelogModalProps) {
  const changelog = useChangelog();

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const changes = (changelog?.history ?? []).filter((entry) => entry.version > analysisVersion);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md max-h-[80vh] overflow-y-auto rounded-3xl bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display font-semibold text-base leading-snug">
            What&rsquo;s changed since this reel was analyzed
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 -mt-2 -mr-2 rounded-full w-8 h-8 flex items-center justify-center hover:bg-surface-2 text-lg"
          >
            ×
          </button>
        </div>

        {changes.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">Loading…</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {changes.map((entry) => (
              <li key={entry.version} className="rounded-2xl bg-surface-2 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-display font-semibold text-sm">{entry.title}</span>
                  <span className="shrink-0 text-[11px] text-ink-muted">
                    v{entry.version}
                    {entry.released_at ? ` · ${entry.released_at}` : ""}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{entry.description}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>,
    document.body
  );
}

export default function VersionChangelogBadge({ analysisVersion }: { analysisVersion: number }) {
  const [open, setOpen] = useState(false);
  const changelog = useChangelog();

  if (!changelog) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="See what changed since this reel was analyzed"
        aria-label="See what changed since this reel was analyzed"
        className="shrink-0 w-5 h-5 rounded-full bg-surface-2 text-ink-muted text-[11px] font-bold flex items-center justify-center hover:bg-line transition-colors"
      >
        ?
      </button>
      {open && (
        <VersionChangelogModal analysisVersion={analysisVersion} onClose={() => setOpen(false)} />
      )}
    </>
  );
}
