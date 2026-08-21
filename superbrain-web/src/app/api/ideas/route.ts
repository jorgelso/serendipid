import { NextRequest, NextResponse } from "next/server";
import { getIdeas } from "@/lib/cache";

// Pure read, no backend round-trip — getIdeas() derives from the already-
// cached /export payload (see src/lib/ideas.ts's v1 tag-frequency note).
export async function GET(request: NextRequest) {
  const themeId = request.nextUrl.searchParams.get("themeId") ?? undefined;
  try {
    const ideas = await getIdeas(themeId);
    return NextResponse.json({ success: true, count: ideas.length, data: ideas });
  } catch {
    return NextResponse.json({ error: "Couldn't compute ideas." }, { status: 500 });
  }
}
