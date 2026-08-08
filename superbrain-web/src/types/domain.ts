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
  category: string | null;
  visual_analysis: string | null;
  audio_transcription: string | null;
  text_analysis: string | null;
  is_hidden: number;
  source_hashtags: string[];
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

export interface SearchSemanticHit {
  shortcode: string;
  similarity: number;
  url: string;
  username: string;
  title: string;
  summary: string;
  tags: string[];
  category: string;
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
