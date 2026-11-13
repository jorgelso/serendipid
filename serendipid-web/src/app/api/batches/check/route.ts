import { NextResponse } from "next/server";
import { SerendipidApiError, checkBatches } from "@/lib/apiClient";

// Manually trigger the backend's batch-completion sweep (ANALYSIS_MODE=batch,
// see backend/core/batch_processor.py). The backend also checks once on its
// own startup; this is the on-demand path since there's no periodic polling.
export async function POST() {
  try {
    const result = await checkBatches();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
