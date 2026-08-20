import { getConfig } from "./config";
import type {
  BatchCheckResponse,
  BulkReanalyzeResponse,
  CategoriesResponse,
  ChangelogResponse,
  ChatMessageExchange,
  ChatThread,
  ChatThreadDetail,
  ExportPayload,
  QueueStatusResponse,
  RatingTier,
  SearchHistoryEntry,
  SearchSemanticResponse,
  ViewHistoryEntry,
} from "@/types/domain";

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
        // Tags post_views/search_queries rows so `next dev` testing traffic
        // never pollutes the recommendation engine's real signal — see the
        // client_env migrations in backend/core/database.py. `next dev` sets
        // NODE_ENV=development automatically; `next start` sets "production".
        "X-Client-Env": process.env.NODE_ENV === "production" ? "prod" : "dev",
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
      `Could not reach the backend at ${config.apiUrl}. ` +
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

export async function fetchChangelog(): Promise<ChangelogResponse> {
  return request<ChangelogResponse>("/changelog");
}

export async function fetchCategories(): Promise<CategoriesResponse> {
  return request<CategoriesResponse>("/categories");
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

export interface DeletePostResponse {
  success: boolean;
  message: string;
  shortcode: string;
}

// Soft delete — the backend sets is_hidden=1 rather than removing the row.
// It's reversible, but only via explicit intent: POST /analyze with
// restore=true restores it instead of re-downloading (see restore_post in
// database.py). A bare resubmission (restore omitted/false, e.g. from an
// automated import/sync script) is a no-op and returns 410 — this app never
// does that today since reanalyzePost() always sets force=true.
export async function deletePost(shortcode: string): Promise<DeletePostResponse> {
  return request<DeletePostResponse>(`/post/${shortcode}`, { method: "DELETE" });
}

export async function fetchQueueStatus(): Promise<QueueStatusResponse> {
  return request<QueueStatusResponse>("/queue-status");
}

// Longer timeout than the default — this can involve several OpenAI
// round-trips server-side (one per in-flight batch job being checked).
const BATCH_CHECK_TIMEOUT_MS = 60 * 1000;

export async function checkBatches(): Promise<BatchCheckResponse> {
  return request<BatchCheckResponse>("/batches/check", {
    method: "POST",
    timeoutMs: BATCH_CHECK_TIMEOUT_MS,
  });
}

// Same idea, but for the separate rescan pipeline's OpenAI batch jobs (see
// backend/core/rescan_batch_processor.py) — distinct endpoint, distinct
// table, on purpose.
export async function checkRescanBatches(): Promise<BatchCheckResponse> {
  return request<BatchCheckResponse>("/rescan/batches/check", {
    method: "POST",
    timeoutMs: BATCH_CHECK_TIMEOUT_MS,
  });
}

// Unlike reanalyzePost(), this returns almost immediately — the backend
// either does a cheap synchronous fix (posts stamped exactly version 7) or
// queues a full re-analysis for the background worker to run later, so it
// never blocks on a subprocess the way a single force-reanalyze does.
export async function bulkReanalyze(shortcodes: string[]): Promise<BulkReanalyzeResponse> {
  return request<BulkReanalyzeResponse>("/reanalyze/bulk", {
    method: "POST",
    body: { shortcodes },
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
  enjoyment_rating?: RatingTier;
  perceived_importance_rating?: RatingTier;
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

interface ChatThreadsResponse {
  success: boolean;
  count: number;
  data: ChatThread[];
}

interface ChatThreadResponse {
  success: boolean;
  data: ChatThread;
}

interface ChatThreadDetailResponse {
  success: boolean;
  data: ChatThreadDetail;
}

interface ChatMessageResponse {
  success: boolean;
  data: ChatMessageExchange;
}

export async function fetchChatThreads(): Promise<ChatThreadsResponse> {
  return request<ChatThreadsResponse>("/chat/threads");
}

export async function createChatThread(): Promise<ChatThreadResponse> {
  return request<ChatThreadResponse>("/chat/threads", { method: "POST", body: {} });
}

export async function fetchChatThread(threadId: string): Promise<ChatThreadDetailResponse> {
  return request<ChatThreadDetailResponse>(`/chat/threads/${threadId}`);
}

export async function deleteChatThread(threadId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/chat/threads/${threadId}`, { method: "DELETE" });
}

// Retrieval + LLM generation can take a while, especially if the primary
// chat provider fails over to a slower fallback — well past the default
// request timeout used for quick reads elsewhere in this file.
const CHAT_MESSAGE_TIMEOUT_MS = 2 * 60 * 1000;

export async function sendChatMessage(threadId: string, message: string): Promise<ChatMessageResponse> {
  return request<ChatMessageResponse>(`/chat/threads/${threadId}/messages`, {
    method: "POST",
    body: { message },
    timeoutMs: CHAT_MESSAGE_TIMEOUT_MS,
    statusMessages: {
      503: "The chatbot couldn't reach any AI provider right now — check the backend's chat provider keys (Gemini/OpenAI) or try again shortly.",
    },
  });
}

// Feeds src/lib/recommendations.ts — never called from a "use client" component.
interface ViewHistoryResponse {
  success: boolean;
  count: number;
  data: ViewHistoryEntry[];
}

export async function fetchViewHistory(limit = 5000): Promise<ViewHistoryResponse> {
  return request<ViewHistoryResponse>("/view-history", { params: { limit } });
}

interface SearchHistoryResponse {
  success: boolean;
  count: number;
  data: SearchHistoryEntry[];
}

export async function fetchSearchHistory(limit = 2000): Promise<SearchHistoryResponse> {
  return request<SearchHistoryResponse>("/search-history", { params: { limit } });
}

// Fire-and-forget from the frontend's view-tracking hook — a failure here
// must never surface to the user, so callers should swallow errors rather
// than propagate this promise's rejection.
export async function logPostView(shortcode: string): Promise<{ success: boolean; shortcode: string }> {
  return request<{ success: boolean; shortcode: string }>(`/post/${shortcode}/view`, { method: "POST" });
}
