import { NextRequest, NextResponse } from "next/server";
import { fetchInstagramExportJob, SuperBrainApiError } from "@/lib/apiClient";

// Poll target for /import's live status view — job status + log_tail.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  try {
    const job = await fetchInstagramExportJob(jobId);
    return NextResponse.json({ data: job });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
