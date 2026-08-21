"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ConfirmDialog from "./ConfirmDialog";

type State = "idle" | "confirming" | "deleting" | "error";

export default function DeleteStudyGuideButton({ id }: { id: number }) {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleConfirm() {
    setState("deleting");
    try {
      const res = await fetch(`/api/study-guides/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete this study guide.");
      router.push("/study-guides");
      router.refresh();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't delete this study guide.");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setState("confirming")}
        className="shrink-0 text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
      >
        🗑 Delete
      </button>

      {(state === "confirming" || state === "deleting" || state === "error") && (
        <ConfirmDialog
          title="Delete this study guide?"
          message={
            "This can't be undone — you'd need to regenerate it (another LLM call) to get it back." +
            (state === "error" && message ? `\n\n${message}` : "")
          }
          confirmLabel={state === "deleting" ? "Deleting…" : "Delete"}
          danger
          busy={state === "deleting"}
          onConfirm={handleConfirm}
          onCancel={() => setState("idle")}
        />
      )}
    </>
  );
}
