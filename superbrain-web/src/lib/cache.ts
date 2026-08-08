import { fetchExport } from "./apiClient";
import { computeThemes } from "./clustering";
import type { ExportPayload, Theme } from "@/types/domain";

interface AppCache {
  exportPayload: ExportPayload | null;
  exportFetchedAt: string | null;
  themes: Theme[] | null;
  unclusteredShortcodes: string[] | null;
  themesComputedAt: string | null;
}

// Stored on globalThis (not a plain module-level variable) so it survives
// Next.js dev-server hot-module-reload re-evaluating this module.
declare global {
  var __superbrainCache: AppCache | undefined;
}

function getCache(): AppCache {
  if (!globalThis.__superbrainCache) {
    globalThis.__superbrainCache = {
      exportPayload: null,
      exportFetchedAt: null,
      themes: null,
      unclusteredShortcodes: null,
      themesComputedAt: null,
    };
  }
  return globalThis.__superbrainCache;
}

export async function getExport(forceRefresh = false): Promise<ExportPayload> {
  const cache = getCache();
  if (!forceRefresh && cache.exportPayload) {
    return cache.exportPayload;
  }
  const payload = await fetchExport();
  cache.exportPayload = payload;
  cache.exportFetchedAt = new Date().toISOString();
  // Invalidate derived themes whenever the underlying export changes.
  cache.themes = null;
  cache.unclusteredShortcodes = null;
  cache.themesComputedAt = null;
  return payload;
}

export async function getThemes(
  forceRefresh = false
): Promise<{ themes: Theme[]; unclusteredShortcodes: string[] }> {
  const cache = getCache();
  const payload = await getExport(forceRefresh);

  if (!forceRefresh && cache.themes && cache.unclusteredShortcodes) {
    return { themes: cache.themes, unclusteredShortcodes: cache.unclusteredShortcodes };
  }

  const { themes, unclusteredShortcodes } = computeThemes(payload.posts);
  cache.themes = themes;
  cache.unclusteredShortcodes = unclusteredShortcodes;
  cache.themesComputedAt = new Date().toISOString();
  return { themes, unclusteredShortcodes };
}

export function invalidateCache(): void {
  const cache = getCache();
  cache.exportPayload = null;
  cache.exportFetchedAt = null;
  cache.themes = null;
  cache.unclusteredShortcodes = null;
  cache.themesComputedAt = null;
}

export function getCacheTimestamps(): { exportFetchedAt: string | null; themesComputedAt: string | null } {
  const cache = getCache();
  return { exportFetchedAt: cache.exportFetchedAt, themesComputedAt: cache.themesComputedAt };
}
