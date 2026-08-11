"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// Generic confirm-before-destructive-action dialog — built on PostModal's
// exact portal/backdrop/Escape/click-outside structure since nothing else in
// this codebase had a confirm pattern before delete/bulk-rescan needed one.
export default function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onCancel, busy]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4"
      onClick={() => !busy && onCancel()}
    >
      <div
        className="w-full max-w-sm rounded-3xl bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-display font-semibold text-lg">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">{message}</p>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded-full border border-line text-ink text-sm font-bold px-4 py-2 disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-full text-sm font-bold px-4 py-2 text-bg disabled:opacity-50 ${
              danger ? "bg-danger" : "bg-ink"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
