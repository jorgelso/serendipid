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
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={state === "loading"}
        className="rounded-full border border-line px-4 py-2 text-xs font-bold text-ink-muted hover:text-coral-ink hover:border-coral transition-colors disabled:opacity-50"
      >
        {state === "loading" ? "Rescanning…" : "↻ Rescan"}
      </button>
      {errorMessage && (
        <p className="absolute right-0 mt-2 w-56 text-xs text-danger text-right">{errorMessage}</p>
      )}
    </div>
  );
}
