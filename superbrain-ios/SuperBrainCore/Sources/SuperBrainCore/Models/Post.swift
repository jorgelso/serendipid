import Foundation

/// Mirrors the backend's full `analyses` row shape (`backend/core/database.py`),
/// as returned by `/export`, `/category/{category}`, and `/search`. There is no
/// `GET /post/{shortcode}` — a full post lookup is always a shortcode search
/// through the cached `/export` payload (`AppDataStore`), exactly like the web
/// frontend's Post Detail page does (`superbrain-web/src/app/post/[shortcode]/page.tsx`).
///
/// `/recent`'s LIGHT_COLUMNS response omits several of these fields, but the
/// web app's own Home feed is powered by the same cached `/export` payload as
/// every other screen (not `/recent`) — this app mirrors that, so there is
/// deliberately only one post model, not a light/full split.
public struct Post: Codable, Identifiable, Hashable, Sendable {
    public var id: String { shortcode }

    public let shortcode: String
    public let url: String
    public let username: String
    public let content_type: String
    public let analyzed_at: String?
    public let updated_at: String?
    public let post_date: String?
    public let likes: Int?
    /// 1-5, nil = unscored. Never treat nil as 0.
    public let importance: Int?
    /// A normal https URL OR a full `data:image/...;base64,...` data URI —
    /// resolve via `MediaResolver`, never assume it's a loadable URL directly.
    public let thumbnail: String?
    public let title: String?
    public let summary: String?
    public let tags: [String]
    public let music: String?
    /// 1-3 values — a post can genuinely belong to multiple categories.
    /// Always a real array server-side, never a bare string.
    public let category: [String]
    /// Usually 1 value, occasionally 2 for bilingual content.
    public let language: [String]
    public let visual_analysis: String?
    public let audio_transcription: String?
    public let text_analysis: String?
    public let is_hidden: Int
    public let source_hashtags: [String]
    public let media_files: [String]
    /// Relative paths ("/media/{shortcode}/...") — prefix with the backend
    /// base URL before use (see `MediaResolver.resolveMediaURLs`).
    public let media_urls: [String]
    public let analysis_version: Int
    public let needs_review: Bool
    /// 1536-dim OpenAI embedding, JSON-text encoded. Only ever parsed by
    /// `EmbeddingMath` for related-posts/clustering — no UI reads it directly.
    public let embedding: String?
    /// User's own subjective judgment — `nil`/`"liked"`/`"loved"`, distinct
    /// from the AI-scored `importance` above. Set via `PUT /post/{shortcode}`.
    public let enjoyment_rating: String?
    public let perceived_importance_rating: String?
    /// AI-judged oratory eloquence, independent of topic (`core/eloquence.py`).
    /// `nil` = not yet scored — never treat that as "not eloquent."
    public let is_eloquent: Bool?
    /// Only meaningful when `is_eloquent == true`: whether the delivery reads
    /// as tutorial-style instruction vs. speech/commentary.
    public let is_tutorial: Bool?
    public let eloquence_rationale: String?

    public init(
        shortcode: String, url: String, username: String, content_type: String,
        analyzed_at: String?, updated_at: String?, post_date: String?, likes: Int?,
        importance: Int?, thumbnail: String?, title: String?, summary: String?,
        tags: [String], music: String?, category: [String], language: [String],
        visual_analysis: String?, audio_transcription: String?, text_analysis: String?,
        is_hidden: Int, source_hashtags: [String], media_files: [String],
        media_urls: [String], analysis_version: Int, needs_review: Bool, embedding: String?,
        enjoyment_rating: String? = nil, perceived_importance_rating: String? = nil,
        is_eloquent: Bool? = nil, is_tutorial: Bool? = nil, eloquence_rationale: String? = nil
    ) {
        self.shortcode = shortcode
        self.url = url
        self.username = username
        self.content_type = content_type
        self.analyzed_at = analyzed_at
        self.updated_at = updated_at
        self.post_date = post_date
        self.likes = likes
        self.importance = importance
        self.thumbnail = thumbnail
        self.title = title
        self.summary = summary
        self.tags = tags
        self.music = music
        self.category = category
        self.language = language
        self.visual_analysis = visual_analysis
        self.audio_transcription = audio_transcription
        self.text_analysis = text_analysis
        self.is_hidden = is_hidden
        self.source_hashtags = source_hashtags
        self.media_files = media_files
        self.media_urls = media_urls
        self.analysis_version = analysis_version
        self.needs_review = needs_review
        self.embedding = embedding
        self.enjoyment_rating = enjoyment_rating
        self.perceived_importance_rating = perceived_importance_rating
        self.is_eloquent = is_eloquent
        self.is_tutorial = is_tutorial
        self.eloquence_rationale = eloquence_rationale
    }
}

/// `POST /analyze` and `/cache/{shortcode}`'s `data` object is a narrower,
/// distinct shape from a full `Post` (no shortcode/media/embedding/etc.) —
/// used only to confirm an ingestion succeeded, not for display elsewhere.
public struct AnalyzedPostSummary: Codable, Sendable {
    public let url: String
    public let username: String
    public let content_type: String
    public let thumbnail: String?
    public let title: String?
    public let summary: String?
    public let tags: [String]
    public let music: String?
    public let category: [String]
    public let needs_review: Bool?
}
