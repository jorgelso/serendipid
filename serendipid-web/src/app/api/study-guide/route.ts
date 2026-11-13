import { NextRequest, NextResponse } from "next/server";
import { generateStudyGuide, SerendipidApiError } from "@/lib/apiClient";

export async function POST(request: NextRequest) {
  let shortcodes: unknown;
  let sourceLabel: unknown;
  let groups: unknown;
  try {
    ({ shortcodes, source_label: sourceLabel, groups } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (!Array.isArray(shortcodes) || shortcodes.length === 0 || !shortcodes.every((s) => typeof s === "string")) {
    return NextResponse.json({ error: "A non-empty 'shortcodes' array is required." }, { status: 400 });
  }
  const validGroups =
    Array.isArray(groups) && groups.every((g) => Array.isArray(g) && g.every((s) => typeof s === "string"))
      ? (groups as string[][])
      : undefined;

  try {
    const result = await generateStudyGuide(
      shortcodes,
      typeof sourceLabel === "string" ? sourceLabel : undefined,
      validGroups
    );
    // No invalidateCache() — generating a study guide doesn't touch any
    // /export-visible post data, just adds rows to separate tables.
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
