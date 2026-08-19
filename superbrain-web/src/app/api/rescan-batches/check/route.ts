import { NextResponse } from "next/server";
import { SuperBrainApiError, checkRescanBatches } from "@/lib/apiClient";

// Manually trigger the backend's rescan-pipeline batch-completion sweep
// (ANALYSIS_MODE=batch, see backend/core/rescan_batch_processor.py) — a
// separate check from /api/batches/check's first-analysis equivalent. The
// backend also checks once on its own startup; this is the on-demand path.
export async function POST() {
  try {
    const result = await checkRescanBatches();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
