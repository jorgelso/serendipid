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
  // 1-5 rating of lasting/reusable value (backend/core/importance.py) — null
  // for posts saved before this feature existed or unscored so far.
  importance: number | null;
  thumbnail: string | null;
  title: string | null;
  summary: string | null;
  // Raw Instagram post caption as written by the creator (scraped at
  // analysis time from media/{shortcode}/info.txt) — distinct from the
  // AI-generated `summary` above. Empty/null for non-Instagram posts, posts
  // with no caption, or posts saved before this was tracked.
  caption: string | null;
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
  // Netflix-style tri-state manual ratings — null (default) | 'liked' | 'loved'.
  // Distinct from the AI-scored `importance` above: these are the user's own
  // subjective judgment, fed into the Home recommendation engine
  // (src/lib/recommendations.ts) alongside implicit view/search signals.
  enjoyment_rating: RatingTier;
  perceived_importance_rating: RatingTier;
  // AI-judged oratory eloquence of audio_transcription (backend/core/
  // eloquence.py) — null for posts not yet scored (distinct from 0/"scored
  // not eloquent"). is_tutorial marks whether an eloquent post is delivered
  // as a tutorial/how-to vs. a speech/commentary; null when is_eloquent
  // itself is null, or if the model didn't return a parseable TUTORIAL field.
  is_eloquent: 0 | 1 | null;
  is_tutorial: 0 | 1 | null;
  eloquence_rationale: string | null;
}

export type RatingTier = "liked" | "loved" | null;

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

// Mirrors backend/api.py's GET /eloquence/overrides (backend/core/database.py's
// eloquence_overrides table) — an audit log of manual "mark as not eloquent"
// corrections made from /eloquent, keeping the AI's original verdict/rationale
// so it can be reviewed later to refine ELOQUENCE_PROMPT (backend/core/eloquence.py).
export interface EloquenceOverride {
  id: number;
  shortcode: string;
  ai_rationale: string | null;
  ai_was_tutorial: 0 | 1 | null;
  overridden_at: string;
}

export interface EloquenceOverridesResponse {
  success: boolean;
  overrides: EloquenceOverride[];
}

export interface CategoriesResponse {
  success: boolean;
  categories: { id: string; name: string; count: number }[];
  // Full canonical taxonomy (backend/core/categories.py), independent of
  // which categories currently have posts.
  canonical: string[];
  total: number;
}

// Mirrors backend/api.py's GET /queue-status. max_concurrent is currently
// always 1 (backend/api.py), so the whole processing_queue is effectively a
// single-file line — see the /versions bulk-rescan progress hook.
export interface QueueStatusResponse {
  currently_processing: string[];
  processing_count: number;
  queue: { shortcode: string; url: string; position: number }[];
  queue_count: number;
  retry_queue: unknown[];
  retry_count: number;
  // ANALYSIS_MODE=batch items in flight (see backend/core/batch_processor.py) —
  // absent nothing, just an empty list, when running in the default "immediate" mode.
  batch_pending: unknown[];
  batch_count: number;
  // Separate surface for the rescan pipeline's own OpenAI batch jobs (see
  // backend/core/rescan_batch_processor.py) — a rescan target is never in
  // currently_processing/queue/batch_pending once it reaches this state.
  rescan_batch_pending: { shortcode: string; phase: string }[];
  rescan_batch_count: number;
  analysis_mode: "immediate" | "batch";
  max_concurrent: number;
  available_slots: number;
}

// Mirrors backend/api.py's POST /batches/check.
export interface BatchCheckResponse {
  success: boolean;
  analysis_mode: "immediate" | "batch";
  summary_advanced?: string[];
  summary_failed?: string[];
  finalized?: string[];
  still_waiting?: string[];
  skipped?: string;
}

// Mirrors backend/api.py's POST /reanalyze/bulk.
export interface BulkReanalyzeResponse {
  success: boolean;
  rescored: string[];
  queued: string[];
  errors: { shortcode: string; error: string }[];
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

// Mirrors backend/api.py's GET /view-history (backend/core/database.py's
// post_views table). Feeds the Home recommendation engine
// (src/lib/recommendations.ts) — never rendered directly.
export interface ViewHistoryEntry {
  shortcode: string;
  viewed_at: string;
}

// Mirrors backend/api.py's GET /search-history (backend/core/database.py's
// search_queries table). query_embedding is only ever consumed inside
// src/lib/recommendations.ts (server-only, same embedding-never-reaches-the-
// browser rule as Post.embedding) — never forward this type to a browser-
// facing response.
export interface SearchHistoryEntry {
  query_text: string;
  query_embedding: number[] | null;
  source: "search" | "chat";
  created_at: string;
}

export type RecommendationStrategy = "cluster" | "vector" | "hybrid";

// src/app/api/recommendations/route.ts's response shape.
export interface RecommendationsResponse {
  success: boolean;
  strategy: RecommendationStrategy;
  coldStart: boolean;
  count: number;
  posts: ClientPost[];
}

// Mirrors backend/core/database.py's study_guides table (backend/core/
// study_guide.py generates the content). shortcodes are the posts actually
// synthesized into `content`; excluded_shortcodes are ones dropped by the
// importance floor before generation (see MIN_STUDY_GUIDE_IMPORTANCE).
//
// role/position: every guide belongs to a collection (see
// StudyGuideCollection below). "final" (position 0) is the one the user
// reads first; at or under MAX_STUDY_GUIDE_POSTS it's the only guide in the
// collection. Above that cap, the pipeline also persists "full" (position
// 1, the whole-selection pass), "merge" (position 2, the combined chunk
// guides), and "chunk" (position 3+, one per chunk) — see
// backend/core/study_guide.py's generate_study_guide_pipeline().
export interface StudyGuide {
  id: number;
  title: string | null;
  content: string;
  shortcodes: string[];
  excluded_shortcodes: string[];
  source_label: string | null;
  created_at: string;
  collection_id: number | null;
  role: "final" | "full" | "merge" | "chunk";
  position: number;
  // The exact OpenAI model that generated this guide (e.g. "gpt-5.6-luna")
  // — null for guides saved before this column existed.
  model: string | null;
}

export interface StudyGuideResponse {
  success: boolean;
  data: StudyGuide;
}

export interface StudyGuidesResponse {
  success: boolean;
  count: number;
  data: StudyGuide[];
}

// Mirrors backend/core/database.py's study_guide_collections table — one
// per generation request, guides already attached and ordered (final,
// full, merge, then chunks) by GET /study-guide-collections[/{id}].
//
// POST /api/study-guide now returns a collection in status "generating"
// with an empty (or partial) `guides` array — the backend runs the actual
// pipeline in a background thread and persists each guide the instant it's
// generated, so the frontend has to poll GET /study-guide-collections[/{id}]
// to watch it fill in rather than trusting the POST response to be final.
// "interrupted" means the backend process died mid-generation (see the
// startup sweep in backend/core/database.py) — whatever guides had already
// been saved are kept, but nothing is still actively generating.
export interface StudyGuideCollection {
  id: number;
  source_label: string | null;
  created_at: string;
  status: "generating" | "complete" | "failed" | "interrupted";
  error: string | null;
  expected_guide_count: number | null;
  guides: StudyGuide[];
}

export interface StudyGuideCollectionResponse {
  success: boolean;
  data: StudyGuideCollection;
}

export interface StudyGuideCollectionsResponse {
  success: boolean;
  count: number;
  data: StudyGuideCollection[];
}

// A recurring idea surfaced by src/lib/ideas.ts's v1 tag-frequency
// aggregation — see that file's module comment for why this is tag-based,
// not the real semantic claim-clustering planned as a v2. Computed entirely
// client/server-side from the cached /export payload; never returned by the
// backend.
export interface Idea {
  tag: string;
  label: string;
  count: number;
  shortcodes: string[];
}

export interface VectorSpacePoint {
  shortcode: string;
  position: [number, number, number];
  colorSlot: VectorSpaceColorSlot;
  themeId: string | null;
  themeLabel: string;
  // Set when this post's embedding sits close to a second theme's centroid
  // as well as its own (e.g. an "AI ethics" post between an AI theme and a
  // religion theme) — see computeVectorSpaceLayout() in vectorSpace.ts.
  // colorSlot/themeId/themeLabel above are unaffected (legend counts and
  // click-filtering stay keyed on the primary theme); this only tells the
  // renderer to blend a second hue into the point's dot color.
  blendColorSlot?: VectorSpaceColorSlot | null;
  blendWeight?: number; // 0-0.5, how much of blendColorSlot to mix in
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
