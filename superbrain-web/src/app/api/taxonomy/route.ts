import { NextResponse } from "next/server";
import { SuperBrainApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { categoryOptions, languageOptions } from "@/lib/posts";

// Autocomplete suggestions for the category/language tag editors — every
// label currently in use across the library. Not a canonical/enforced list
// (the backend doesn't validate against one either): editing can still add a
// brand-new label by typing it, this just helps avoid accidental duplicates
// like "guitar" vs "Guitar".
export async function GET() {
  try {
    const { posts } = await getExport();
    return NextResponse.json({
      categories: categoryOptions(posts),
      languages: languageOptions(posts),
    });
  } catch (err) {
    if (err instanceof SuperBrainApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
