import { NextRequest, NextResponse } from "next/server";
import { flushRetryQueue, SuperBrainApiError } from "@/lib/apiClient";

// Promotes retry-queued reels back into the active queue. `force` skips their
// scheduled wait entirely. No invalidateCache(): nothing is analyzed here,
// items are only moved between processing_queue statuses — the analyses each
// one eventually produces land via the queue worker, long after this returns.
export async function POST(request: NextRequest) {
  const force = request.nextUrl.searchParams.get("force") === "true";
  try {
    return NextResponse.json(await flushRetryQueue(force));
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
