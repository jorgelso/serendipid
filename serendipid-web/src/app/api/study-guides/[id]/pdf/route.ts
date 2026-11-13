import { NextRequest, NextResponse } from "next/server";
import { fetchStudyGuideAsset, SerendipidApiError } from "@/lib/apiClient";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const { body, contentType } = await fetchStudyGuideAsset(id, "pdf");
    return new NextResponse(body, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "private, max-age=60",
      },
    });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
