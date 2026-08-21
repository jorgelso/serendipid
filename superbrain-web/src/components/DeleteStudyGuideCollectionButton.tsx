"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ConfirmDialog from "./ConfirmDialog";

type State = "idle" | "confirming" | "deleting" | "error";

export default function DeleteStudyGuideCollectionButton({ id, guideCount }: { id: number; guideCount: number }) {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleConfirm() {
    setState("deleting");
    try {
      const res = await fetch(`/api/study-guide-collections/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete this collection.");
      router.refresh();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Couldn't delete this collection.");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          setState("confirming");
        }}
        className="shrink-0 text-xs font-bold text-coral-ink hover:opacity-70 transition-opacity"
      >
        🗑 Delete
      </button>

      {(state === "confirming" || state === "deleting" || state === "error") && (
        <ConfirmDialog
          title="Delete this study guide collection?"
          message={
            `This deletes all ${guideCount} guide${guideCount === 1 ? "" : "s"} in it — the final guide and every intermediate one. Can't be undone without regenerating (another round of LLM calls).` +
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
