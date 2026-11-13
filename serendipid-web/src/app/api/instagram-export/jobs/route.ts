import { NextRequest, NextResponse } from "next/server";
import { SerendipidApiError, createInstagramExportJob, fetchInstagramExportJobs } from "@/lib/apiClient";
import { looksLikeAllPostsExport, looksLikeCollectionsExport } from "@/lib/instagramExportValidation";

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
    if (!looksLikeCollectionsExport(exportData)) {
      return NextResponse.json(
        {
          error:
            'That file doesn\'t look like an Instagram "by collection" export — expected a JSON ' +
            "list of collections, each with a Name and a list of saved posts.",
        },
        { status: 400 }
      );
    }

    let allPostsData: unknown;
    const allPostsFile = formData.get("allPostsFile");
    if (allPostsFile instanceof File) {
      try {
        allPostsData = JSON.parse(await allPostsFile.text());
      } catch {
        return NextResponse.json({ error: "The all-posts file isn't valid JSON." }, { status: 400 });
      }
      if (!looksLikeAllPostsExport(allPostsData)) {
        return NextResponse.json(
          {
            error:
              'That all-posts file doesn\'t look like an Instagram "all posts" export — expected a ' +
              "flat JSON list of individually-saved posts, each with a URL and a save timestamp.",
          },
          { status: 400 }
        );
      }
    }

    const modeField = formData.get("mode");
    const mode = modeField === "by_collection" ? "by_collection" : "regular";
    const priorityFolderField = formData.get("priorityFolder");
    const priorityFolder = typeof priorityFolderField === "string" && priorityFolderField ? priorityFolderField : null;
    // Off unless explicitly "true" — matches the backend/CLI default (see
    // scripts/import_saved_instagram.py's --reverse-collections docstring).
    const reverseCollections = formData.get("reverseCollections") === "true";

    const job = await createInstagramExportJob({
      exportData, allPostsData, mode, priorityFolder, reverseCollections,
    });
    return NextResponse.json({ data: job });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
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
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
