import { NextResponse } from "next/server";
import { SerendipidApiError, checkEloquenceBatches } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Third batch-completion sweep, for the eloquence backfill's OpenAI Batch
// jobs (backend/core/eloquence_batch_processor.py) — distinct from
// /api/batches/check and /api/rescan-batches/check on purpose. Unlike those
// two, a finished job here writes is_eloquent straight into `analyses`, which
// the cached /export payload (and so the /eloquent feed) reads — hence the
// invalidateCache() when anything was actually scored.
export async function POST() {
  try {
    const result = await checkEloquenceBatches();
    if ((result.scored?.length ?? 0) > 0) invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
