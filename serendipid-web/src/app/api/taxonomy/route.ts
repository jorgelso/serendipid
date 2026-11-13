import { NextResponse } from "next/server";
import { fetchCategories, SerendipidApiError } from "@/lib/apiClient";
import { getExport } from "@/lib/cache";
import { categoryOptions, languageOptions } from "@/lib/posts";

// Autocomplete suggestions for the category/language tag editors. Categories
// are every canonical label (backend/core/categories.py) unioned with any
// label actually in use across the library — the union covers legacy/
// freeform labels a post might still carry that aren't in the canonical set.
// Languages have no canonical list, so they stay purely usage-derived. This
// is still not an enforced list (the backend doesn't validate category
// against one either): editing can add a brand-new label by typing it, this
// just helps avoid accidental duplicates like "guitar" vs "Guitar".
export async function GET() {
  try {
    const [{ posts }, { canonical }] = await Promise.all([getExport(), fetchCategories()]);
    const categories = Array.from(new Set([...canonical, ...categoryOptions(posts)])).sort();
    return NextResponse.json({
      categories,
      languages: languageOptions(posts),
    });
  } catch (err) {
    if (err instanceof SerendipidApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status ?? 502 });
    }
    return NextResponse.json({ error: "Unexpected error." }, { status: 500 });
  }
}
