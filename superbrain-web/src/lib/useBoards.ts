"use client";

import { useEffect, useState } from "react";
import type { Board } from "@/types/domain";

// Fetch-once-and-share for the browser tab, same hand-rolled pattern as
// useChangelog.ts — many PostCards/PostDetail instances on a page all want
// the same board list. Unlike the changelog (effectively static), board
// membership changes constantly from several different UI entry points
// (Browse cards, the post modal, the full post page, the /boards page
// itself), so this also supports pushing a refresh out to every mounted
// consumer via refreshBoards() rather than only caching the first fetch.
let cached: Board[] | null = null;
let inflight: Promise<Board[]> | null = null;
const subscribers = new Set<(boards: Board[]) => void>();

async function loadBoards(): Promise<Board[]> {
  if (cached) return cached;
  if (!inflight) {
    inflight = fetch("/api/boards")
      .then((res) => res.json())
      .then((data: { data?: Board[] }) => {
        const boards = data.data ?? [];
        cached = boards;
        return boards;
      })
      .catch(() => [])
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Call after any board/subcollection mutation (create/rename/delete, add/remove
 * a post) so every mounted useBoards() consumer picks up the change. */
export async function refreshBoards(): Promise<Board[]> {
  cached = null;
  const boards = await loadBoards();
  subscribers.forEach((fn) => fn(boards));
  return boards;
}

export function useBoards(): Board[] | null {
  const [data, setData] = useState<Board[] | null>(cached);

  useEffect(() => {
    subscribers.add(setData);
    if (!cached) {
      loadBoards().then(setData);
    }
    return () => {
      subscribers.delete(setData);
    };
  }, []);

  return data;
}
