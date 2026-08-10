// Shapes mirror backend/api.py's /export and /search/semantic responses exactly
// (backend/core/database.py's analyses table + _row_to_dict/_collection_row_to_dict).

export interface Post {
  shortcode: string;
  url: string;
  username: string;
  content_type: string;
  analyzed_at: string | null;
  updated_at: string | null;
  post_date: string | null;
  likes: number | null;
  thumbnail: string | null;
  title: string | null;
  summary: string | null;
  tags: string[];
  music: string | null;
  // A post can genuinely belong to 1-3 categories (backend/core/categories.py's
  // ~30-label taxonomy) — stored as a JSON array server-side, same pattern as
  // `tags`. Never a plain string anymore, even for single-category posts.
  category: string[];
  // Content language(s) actually spoken/shown on-screen (backend/core/languages.py)
  // — a separate axis from category, same JSON-array storage pattern. Usually
  // one entry, occasionally two for genuinely bilingual content.
  language: string[];
  visual_analysis: string | null;
  audio_transcription: string | null;
  text_analysis: string | null;
  is_hidden: number;
  source_hashtags: string[];
  // Filenames/paths for the permanently-stored original media (backend/core/
  // media_store.py). Carousels use numbered entries ("1.mp4", "2.jpg", ...)
  // instead of "video.mp4"/"thumbnail.jpg". Empty arrays mean nothing was
  // downloaded for this post (content_type === "instagram" with no .mp4 here
  // is the "missing video, needs re-fetch" case — see lib/media.ts).
  media_files: string[];
  // Same list as media_files, already relative paths ("/media/{shortcode}/...").
  // Resolved to absolute URLs server-side (see lib/posts.ts toDisplayPost) —
  // the /media mount has no auth dependency, same as /static.
  media_urls: string[];
  // analysis_version / needs_review: added when the category taxonomy was
  // overhauled (backend/core/database.py CURRENT_ANALYSIS_VERSION). A post
  // whose analysis_version is behind the current pipeline version is flagged
  // needs_review so the UI can surface it and offer to re-run or dismiss.
  analysis_version: number;
  needs_review: boolean;
  // Raw JSON-text TEXT column as /export returns it (1536-dim OpenAI vector).
  // Only ever parsed server-side for clustering — never sent to the client.
  embedding: string | null;
}

// Post shape safe to send to the browser: embedding stripped.
export type ClientPost = Omit<Post, "embedding">;

export interface Collection {
  id: string;
  name: string;
  icon: string | null;
  post_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ExportPayload {
  version: string;
  exported_at: string;
  posts: Post[];
  collections: Collection[];
  stats: Record<string, unknown>;
}

// Mirrors backend/api.py's GET /changelog (backend/core/database.py's
// analysis_changelog table) — newest version first. Used to turn a post's
// bare `analysis_version` into a human-readable "N versions behind" and to
// list what changed since it was analyzed.
export interface ChangelogEntry {
  version: number;
  released_at: string | null;
  title: string;
  description: string;
}

export interface ChangelogResponse {
  success: boolean;
  current_version: number | null;
  history: ChangelogEntry[];
}

export interface CategoriesResponse {
  success: boolean;
  categories: { id: string; name: string; count: number }[];
  // Full canonical taxonomy (backend/core/categories.py), independent of
  // which categories currently have posts.
  canonical: string[];
  total: number;
}

export interface SearchSemanticHit {
  shortcode: string;
  similarity: number;
  url: string;
  username: string;
  title: string;
  summary: string;
  tags: string[];
  category: string[];
  thumbnail: string;
}

export interface SearchSemanticResponse {
  success: boolean;
  query: string;
  count: number;
  data: SearchSemanticHit[];
}

export interface MicroCluster {
  id: string;
  label: string;
  subLabels: string[];
  postShortcodes: string[];
}

export interface Theme {
  id: string;
  label: string;
  subLabels: string[];
  postCount: number;
  microClusters: MicroCluster[];
}

// A post plotted in the 3D vector-space view (src/app/space). Deliberately as
// light as ClientPost's fuller shape — no summary/transcripts/embedding, just
// enough to render a point, a hover preview, and a click-through lookup by
// shortcode. "theme-N" (N = 0-7) selects one of the 8 validated categorical
// hues in src/app/globals.css (--viz-series-1..8); "other" is every theme
// past the 8th, ranked by size; "unclustered" is a post with no theme at all
// (see computeThemes()'s unclusteredShortcodes). All three render as the
// shared --viz-neutral color, distinguished only by their (always-visible)
// legend/hover label — see dataviz skill's relief rule.
export type VectorSpaceColorSlot = `theme-${number}` | "other" | "unclustered";

// Mirrors backend/core/rag.py's _light_source() — the citation shape
// attached to an assistant chat message, not the full retrieved post (no
// audio_transcription/visual_analysis/text_analysis, same idea as
// ClientPost stripping `embedding`). No `thumbnail` either — that's
// resolved client-side via /api/thumbnail/{shortcode} (see ChatSourceCards)
// instead of embedding a base64 blob in every stored chat message.
export interface ChatSource {
  shortcode: string;
  similarity: number;
  url: string;
  username: string;
  title: string;
  summary: string;
  tags: string[];
  category: string[] | string;
}

// Mirrors backend/core/database.py's chat_messages table /
// _chat_message_row_to_dict (sources is JSON-decoded server-side).
export interface ChatMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  created_at: string;
}

// Mirrors backend/core/database.py's chat_threads table.
export interface ChatThread {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

// GET /chat/threads/{id}'s response shape (thread + full message history).
export interface ChatThreadDetail extends ChatThread {
  messages: ChatMessage[];
}

// POST /chat/threads/{id}/messages's response shape.
export interface ChatMessageExchange {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

export interface VectorSpacePoint {
  shortcode: string;
  position: [number, number, number];
  colorSlot: VectorSpaceColorSlot;
  themeId: string | null;
  themeLabel: string;
  title: string | null;
  category: string[];
  thumbnail: string | null;
  videoUrl: string | null;
  // Density-based glow scaling disabled (reverted to neutral-slot-based
  // dimming in VectorSpaceScene.tsx) — field commented out, not deleted, in
  // case it's wanted again later. Was: 0-1, based on how many other points
  // sit within a fixed radius of this one (see computeGlowScales() in
  // src/lib/vectorSpace.ts) — 1 for an isolated point, down to a floor for
  // one buried in a dense cluster.
  // glowScale: number;
}
