"use client";

import { useEffect, useState } from "react";
import type { ChangelogResponse } from "@/types/domain";

// Fetch-once-and-share for the browser tab: many PostCards on a feed page
// each want the changelog, but it's the same data for all of them and rarely
// changes, so a single in-flight/cached promise (not React Query/SWR — this
// app hand-rolls this pattern, see InfiniteFeed's own client fetch) is enough
// to avoid one /api/changelog request per card.
let cached: ChangelogResponse | null = null;
let inflight: Promise<ChangelogResponse | null> | null = null;

async function loadChangelog(): Promise<ChangelogResponse | null> {
  if (cached) return cached;
  if (!inflight) {
    inflight = fetch("/api/changelog")
      .then((res) => res.json())
      .then((data: ChangelogResponse) => {
        cached = data;
        return data;
      })
      .catch(() => null)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function useChangelog(): ChangelogResponse | null {
  const [data, setData] = useState<ChangelogResponse | null>(cached);

  useEffect(() => {
    if (data) return;
    let alive = true;
    loadChangelog().then((result) => {
      if (alive) setData(result);
    });
    return () => {
      alive = false;
    };
  }, [data]);

  return data;
}
