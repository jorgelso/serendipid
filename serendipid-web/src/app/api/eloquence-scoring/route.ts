import { NextRequest, NextResponse } from "next/server";
import { startEloquenceScoring, SerendipidApiError } from "@/lib/apiClient";

// Kicks off a backend background job scoring the first `limit` candidates
// (null = all). Returns immediately; progress is polled via
// /api/eloquence-scoring/status, which is also where the cache gets
// invalidated once the job has actually written verdicts.
export async function POST(request: NextRequest) {
  let body: { limit?: unknown; force?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const limit = body.limit ?? null;
  if (limit !== null && (!Number.isInteger(limit) || (limit as number) < 1)) {
    return NextResponse.json({ error: "'limit' must be a positive integer or null." }, { status: 400 });
  }

  try {
    const result = await startEloquenceScoring({ limit: limit as number | null, force: body.force === true });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
