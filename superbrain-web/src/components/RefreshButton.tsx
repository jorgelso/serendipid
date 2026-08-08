"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function RefreshButton() {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleClick() {
    setState("loading");
    setErrorMessage(null);
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error ?? "Refresh failed.");
      }
      setState("idle");
      router.refresh();
    } catch (err) {
      setState("error");
      setErrorMessage(err instanceof Error ? err.message : "Refresh failed.");
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleClick}
        disabled={state === "loading"}
        className="font-label text-[11px] uppercase tracking-wide text-ink-muted hover:text-moss transition-colors disabled:opacity-50"
      >
        {state === "loading" ? "Rescanning…" : "Rescan library"}
      </button>
      {errorMessage && <p className="text-xs text-danger max-w-xs text-right">{errorMessage}</p>}
    </div>
  );
}
