import { getConfig } from "./config";
import type { ExportPayload, SearchSemanticResponse } from "@/types/domain";

export class SuperBrainApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "SuperBrainApiError";
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number>;
  timeoutMs?: number;
  // Per-call overrides for specific status codes, since the same code can
  // mean different things on different endpoints (e.g. 503 means "no
  // OPENAI_API_KEY" on /search/semantic but "analysis queue busy" on /analyze).
  statusMessages?: Partial<Record<number, string>>;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const config = getConfig();
  const url = new URL(`${config.apiUrl}${path}`);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    url.searchParams.set(key, String(value));
  }
  const timeoutMs = options.timeoutMs ?? config.requestTimeoutMs;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: options.method ?? "GET",
      headers: {
        "X-API-Key": config.apiKey,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new SuperBrainApiError(
        `Request to ${url.toString()} timed out after ${timeoutMs}ms.`
      );
    }
    throw new SuperBrainApiError(
      `Could not reach the SuperBrain backend at ${config.apiUrl}. ` +
        "Check that it's running and that SUPERBRAIN_API_URL is correct."
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!res.ok) {
    // Drain the body exactly once, regardless of which branch below throws —
    // leaving it unconsumed was leaving the underlying gzip/keep-alive stream
    // dangling, which is what caused the MaxListenersExceededWarning on Gzip.
    const body = await res.text().catch(() => "");

    if (res.status === 401) {
      throw new SuperBrainApiError(
        "Backend rejected the API key (401). Check SUPERBRAIN_API_KEY.",
        401
      );
    }
    if (options.statusMessages?.[res.status]) {
      throw new SuperBrainApiError(options.statusMessages[res.status]!, res.status);
    }
    if (res.status === 503) {
      throw new SuperBrainApiError(
        "Backend could not generate an embedding (503) — is OPENAI_API_KEY " +
          "configured on the backend? Semantic search is unavailable.",
        503
      );
    }
    throw new SuperBrainApiError(
      `Backend error ${res.status} calling ${path}: ${body.slice(0, 300)}`,
      res.status
    );
  }

  return (await res.json()) as T;
}

export async function fetchExport(limit = 50000, offset = 0): Promise<ExportPayload> {
  return request<ExportPayload>("/export", { params: { limit, offset, format: "json" } });
}

export async function fetchSemanticSearch(
  q: string,
  limit = 20,
  minSimilarity = 0
): Promise<SearchSemanticResponse> {
  return request<SearchSemanticResponse>("/search/semantic", {
    params: { q, limit, min_similarity: minSimilarity },
  });
}

export interface ReanalyzeResponse {
  success: boolean;
  cached: boolean;
  data?: Record<string, unknown>;
  error?: string;
  processing_time?: number;
}

// The full pipeline (video download, vision, transcription, music ID) runs
// synchronously on the backend for a forced re-analysis — this can take
// minutes, well past the default request timeout used everywhere else.
const REANALYZE_TIMEOUT_MS = 5 * 60 * 1000;

export async function reanalyzePost(url: string): Promise<ReanalyzeResponse> {
  return request<ReanalyzeResponse>("/analyze", {
    method: "POST",
    body: { url, force: true },
    timeoutMs: REANALYZE_TIMEOUT_MS,
    statusMessages: {
      409: "This post is already being analyzed — wait a moment and try again.",
      503: "The backend is busy analyzing another post right now — try again shortly.",
    },
  });
}

export interface UpdatePostResponse {
  success: boolean;
  message: string;
  shortcode: string;
  updated_fields: string[];
}

export async function markReviewed(shortcode: string): Promise<UpdatePostResponse> {
  return request<UpdatePostResponse>(`/post/${shortcode}`, {
    method: "PUT",
    body: { reviewed: true },
  });
}

export interface PostEdits {
  title?: string;
  summary?: string;
  category?: string[];
  language?: string[];
}

// The backend's PUT /post/{shortcode} does not validate category/language
// against any canonical list — it accepts any strings, JSON-encodes them,
// and overwrites the column. No enum enforcement to mirror here.
export async function updatePost(shortcode: string, edits: PostEdits): Promise<UpdatePostResponse> {
  return request<UpdatePostResponse>(`/post/${shortcode}`, {
    method: "PUT",
    body: edits,
  });
}
