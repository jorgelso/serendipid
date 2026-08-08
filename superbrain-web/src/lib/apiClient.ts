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

async function request<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const config = getConfig();
  const url = new URL(`${config.apiUrl}${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    url.searchParams.set(key, String(value));
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      headers: { "X-API-Key": config.apiKey },
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new SuperBrainApiError(
        `Request to ${url.toString()} timed out after ${config.requestTimeoutMs}ms.`
      );
    }
    throw new SuperBrainApiError(
      `Could not reach the SuperBrain backend at ${config.apiUrl}. ` +
        "Check that it's running and that SUPERBRAIN_API_URL is correct."
    );
  } finally {
    clearTimeout(timeout);
  }

  if (res.status === 401) {
    throw new SuperBrainApiError(
      "Backend rejected the API key (401). Check SUPERBRAIN_API_KEY.",
      401
    );
  }
  if (res.status === 503) {
    throw new SuperBrainApiError(
      "Backend could not generate an embedding (503) — is OPENAI_API_KEY " +
        "configured on the backend? Semantic search is unavailable.",
      503
    );
  }
  if (!res.ok) {
    const body = await res.text();
    throw new SuperBrainApiError(
      `Backend error ${res.status} calling ${path}: ${body.slice(0, 300)}`,
      res.status
    );
  }

  return (await res.json()) as T;
}

export async function fetchExport(limit = 50000, offset = 0): Promise<ExportPayload> {
  return request<ExportPayload>("/export", { limit, offset, format: "json" });
}

export async function fetchSemanticSearch(
  q: string,
  limit = 20,
  minSimilarity = 0
): Promise<SearchSemanticResponse> {
  return request<SearchSemanticResponse>("/search/semantic", {
    q,
    limit,
    min_similarity: minSimilarity,
  });
}
