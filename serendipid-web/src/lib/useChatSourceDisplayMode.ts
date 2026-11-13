"use client";

import { useSyncExternalStore } from "react";

export type ChatSourceDisplayMode = "always" | "on-demand";

const STORAGE_KEY = "serendipid:chat-source-display-mode";
const DEFAULT_MODE: ChatSourceDisplayMode = "always";

function isValidMode(value: string | null): value is ChatSourceDisplayMode {
  return value === "always" || value === "on-demand";
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ChatSourceDisplayMode {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isValidMode(stored) ? stored : DEFAULT_MODE;
}

function getServerSnapshot(): ChatSourceDisplayMode {
  return DEFAULT_MODE;
}

// No user-account concept in this app (a single shared X-API-Key), so a
// per-browser localStorage preference is the natural fit for a UI-only
// setting like this. useSyncExternalStore — not useState+useEffect — is
// what avoids a hydration mismatch here: it renders DEFAULT_MODE during
// SSR/hydration (localStorage doesn't exist server-side, so the client's
// first render must match that default too) and only switches to the real
// stored value in the render immediately after hydration completes. This
// is the pattern React designed this hook for.
export function useChatSourceDisplayMode(): [ChatSourceDisplayMode, (mode: ChatSourceDisplayMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function setMode(next: ChatSourceDisplayMode) {
    window.localStorage.setItem(STORAGE_KEY, next);
    listeners.forEach((listener) => listener());
  }

  return [mode, setMode];
}
