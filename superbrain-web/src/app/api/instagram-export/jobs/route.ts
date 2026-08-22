import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError, createInstagramExportJob, fetchInstagramExportJobs } from "@/lib/apiClient";

// Kicks off a background Instagram-export import job (multipart file +
// mode/priorityFolder/reverseCollections fields, sent from /import's
// "Start import" button) — see backend's POST /instagram-export/jobs.
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "No file uploaded." }, { status: 400 });
    }

    let exportData: unknown;
    try {
      exportData = JSON.parse(await file.text());
    } catch {
      return NextResponse.json({ error: "That file isn't valid JSON." }, { status: 400 });
    }

    const modeField = formData.get("mode");
    const mode = modeField === "by_collection" ? "by_collection" : "regular";
    const priorityFolderField = formData.get("priorityFolder");
    const priorityFolder = typeof priorityFolderField === "string" && priorityFolderField ? priorityFolderField : null;
    const reverseCollections = formData.get("reverseCollections") !== "false";

    const job = await createInstagramExportJob({ exportData, mode, priorityFolder, reverseCollections });
    return NextResponse.json({ data: job });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}

export async function GET() {
  try {
    const jobs = await fetchInstagramExportJobs();
    return NextResponse.json({ data: jobs });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
