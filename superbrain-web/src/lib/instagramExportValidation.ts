// Structural validation for the two Instagram export shapes /import
// accepts. Mirrors backend/scripts/import_saved_instagram.py's
// looks_like_collections_export()/looks_like_all_posts_export() exactly —
// keep the two in sync if either changes. This exists as a real,
// server-side (Next.js Route Handler) check, not just a client-side
// convenience: a request can reach these route handlers directly, bypassing
// whatever the browser page does, so the actual enforcement has to live
// here (and again, independently, in the backend — see
// _validate_instagram_export_shapes() in api.py — since a caller could
// also skip this Next.js layer entirely and hit the backend API directly).

interface LabelValueEntry {
  label?: unknown;
  dict?: unknown;
  [key: string]: unknown;
}

function asLabelValues(item: unknown): LabelValueEntry[] | null {
  if (!item || typeof item !== "object") return null;
  const lv = (item as Record<string, unknown>).label_values;
  return Array.isArray(lv) ? (lv as LabelValueEntry[]) : null;
}

/** Does data look like a saved_collections.json-shaped export (top-level
 * list, at least one item with a label_values list containing both a Name
 * label and a Media-like dict entry)? */
export function looksLikeCollectionsExport(data: unknown): boolean {
  if (!Array.isArray(data) || data.length === 0) return false;
  return data.some((item) => {
    const labelValues = asLabelValues(item);
    if (!labelValues) return false;
    const hasName = labelValues.some((lv) => lv && typeof lv === "object" && lv.label === "Name");
    const hasMedia = labelValues.some((lv) => lv && typeof lv === "object" && "dict" in lv);
    return hasName && hasMedia;
  });
}

/** Does data look like a saved_posts.json-shaped export (top-level list,
 * at least one item with its own numeric top-level `timestamp` and a
 * label_values list containing a URL directly)? Both shapes' top-level
 * items can carry a `timestamp` (a collections file's is collection-level),
 * so `timestamp` alone isn't a reliable signal — the URL-vs-Name label is
 * what actually distinguishes the two. */
export function looksLikeAllPostsExport(data: unknown): boolean {
  if (!Array.isArray(data) || data.length === 0) return false;
  return data.some((item) => {
    const labelValues = asLabelValues(item);
    if (!labelValues) return false;
    const timestamp = (item as Record<string, unknown>).timestamp;
    if (typeof timestamp !== "number") return false;
    return labelValues.some((lv) => lv && typeof lv === "object" && lv.label === "URL");
  });
}
