import { NextResponse } from "next/server";
import { fetchStudyGuideCollections, SerendipidApiError } from "@/lib/apiClient";

export async function GET() {
  try {
    const result = await fetchStudyGuideCollections();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
