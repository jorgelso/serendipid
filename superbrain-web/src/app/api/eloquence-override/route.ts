import { NextRequest, NextResponse } from "next/server";
import { overrideEloquence, SuperBrainApiError } from "@/lib/apiClient";
import { invalidateCache } from "@/lib/cache";

export async function POST(request: NextRequest) {
  let shortcodes: unknown;
  try {
    ({ shortcodes } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (!Array.isArray(shortcodes) || shortcodes.length === 0 || !shortcodes.every((s) => typeof s === "string")) {
    return NextResponse.json({ error: "A non-empty 'shortcodes' array is required." }, { status: 400 });
  }

  try {
    const result = await overrideEloquence(shortcodes);
    invalidateCache();
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
