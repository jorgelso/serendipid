import { NextRequest, NextResponse } from "next/server";
import { SuperBrainApiError, previewInstagramExport } from "@/lib/apiClient";

// Reads an uploaded Instagram "Download Your Information" export JSON
// (multipart, sent from /import's file input) and forwards its parsed
// content to the backend for a per-category count preview — lets the page
// sanity-check the file and populate the priority-folder dropdown before
// committing to an hours-long import job.
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

    const preview = await previewInstagramExport(exportData);
    return NextResponse.json(preview);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
