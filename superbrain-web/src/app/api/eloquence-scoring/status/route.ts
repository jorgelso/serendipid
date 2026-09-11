import { NextResponse } from "next/server";
import { fetchEloquenceScoringStatus, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

// Polled by the admin panel while a scoring job runs. The job writes
// is_eloquent into `analyses` as it goes, so the cached /export payload
// (which feeds /eloquent) goes stale mid-run — invalidate on every poll
// that observes a job that has scored something, not just at completion,
// so the /eloquent feed picks up verdicts as they land rather than only
// after the last of a 1000-post run.
export async function GET() {
  try {
    const result = await fetchEloquenceScoringStatus();
    const job = result.data;
    if (job && (job.eloquent + job.not_eloquent > 0)) invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
