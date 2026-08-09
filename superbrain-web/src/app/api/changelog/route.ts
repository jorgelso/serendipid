import { NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getChangelog } from "@/lib/cache";

// Powers the "N versions behind" badges and their what-changed popup on
// reels analyzed under an older pipeline version — see CURRENT_ANALYSIS_VERSION
// in backend/core/database.py.
export async function GET() {
  try {
    const changelog = await getChangelog();
    return NextResponse.json(changelog);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
