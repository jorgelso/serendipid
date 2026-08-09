import { fetchChangelog, fetchExport } from "./apiClient";
import { computeThemes } from "./clustering";
import { getConfig } from "./config";
import { computeVectorSpaceLayout } from "./vectorSpace";
import type { ChangelogResponse, ExportPayload, Theme, VectorSpacePoint } from "@/types/domain";

interface AppCache {
  exportPayload: ExportPayload | null;
  exportFetchedAt: string | null;
  themes: Theme[] | null;
  unclusteredShortcodes: string[] | null;
  themesComputedAt: string | null;
  vectorSpace: VectorSpacePoint[] | null;
  vectorSpaceComputedAt: string | null;
  changelog: ChangelogResponse | null;
  changelogFetchedAt: string | null;
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
      vectorSpace: null,
      vectorSpaceComputedAt: null,
      changelog: null,
      changelogFetchedAt: null,
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
  // Invalidate derived themes/vector-space whenever the underlying export changes.
  cache.themes = null;
  cache.unclusteredShortcodes = null;
  cache.themesComputedAt = null;
  cache.vectorSpace = null;
  cache.vectorSpaceComputedAt = null;
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

// UMAP is the expensive step (unlike the O(n^2) but much cheaper cosine
// clustering above), so its result is cached separately and keyed off the
// same forceRefresh flag rather than recomputed on every /space request.
export async function getVectorSpace(forceRefresh = false): Promise<VectorSpacePoint[]> {
  const cache = getCache();
  if (!forceRefresh && cache.vectorSpace) {
    return cache.vectorSpace;
  }

  // getExport(forceRefresh) is the one call that decides whether to hit the
  // backend; once its cache is populated, getThemes(false) reads straight
  // from it instead of triggering a second redundant fetch.
  const payload = await getExport(forceRefresh);
  const { themes } = await getThemes(false);
  const points = computeVectorSpaceLayout(payload.posts, themes, getConfig().apiUrl);
  cache.vectorSpace = points;
  cache.vectorSpaceComputedAt = new Date().toISOString();
  return points;
}

// Not touched by invalidateCache() — the changelog doesn't change when posts
// are mutated (reanalyze/mark-reviewed/update-post), it's independent,
// slow-changing data.
export async function getChangelog(forceRefresh = false): Promise<ChangelogResponse> {
  const cache = getCache();
  if (!forceRefresh && cache.changelog) {
    return cache.changelog;
  }
  const payload = await fetchChangelog();
  cache.changelog = payload;
  cache.changelogFetchedAt = new Date().toISOString();
  return payload;
}

export function invalidateCache(): void {
  const cache = getCache();
  cache.exportPayload = null;
  cache.exportFetchedAt = null;
  cache.themes = null;
  cache.unclusteredShortcodes = null;
  cache.themesComputedAt = null;
  cache.vectorSpace = null;
  cache.vectorSpaceComputedAt = null;
}

export function getCacheTimestamps(): {
  exportFetchedAt: string | null;
  themesComputedAt: string | null;
  vectorSpaceComputedAt: string | null;
} {
  const cache = getCache();
  return {
    exportFetchedAt: cache.exportFetchedAt,
    themesComputedAt: cache.themesComputedAt,
    vectorSpaceComputedAt: cache.vectorSpaceComputedAt,
  };
}
