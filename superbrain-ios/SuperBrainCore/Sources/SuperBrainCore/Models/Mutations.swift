import Foundation

/// `POST /analyze` request body — used both for fresh ingestion (Share
/// Extension) and, with `force: true`, for the Post Detail "Re-run analysis"
/// action.
public struct AnalyzeRequest: Encodable, Sendable {
    public let url: String
    public let force: Bool?
    /// Explicit intent required to bring a soft-deleted post back (backend
    /// no-ops a bare resubmission otherwise). Sharing/re-sharing a URL is a
    /// deliberate user action, so the Share Extension passes true.
    public let restore: Bool?
    public let caption: String?
    public let hashtags: [String]?

    public init(url: String, force: Bool? = nil, restore: Bool? = nil, caption: String? = nil, hashtags: [String]? = nil) {
        self.url = url
        self.force = force
        self.restore = restore
        self.caption = caption
        self.hashtags = hashtags
    }
}

/// `POST /analyze`'s response shape.
public struct AnalysisResponse: Codable, Sendable {
    public let success: Bool
    public let cached: Bool
    public let data: AnalyzedPostSummary?
    public let error: String?
    public let processing_time: Double?
}

/// `PUT /post/{shortcode}` body — the backend only honors these 5 keys, all
/// optional; anything else is silently dropped, and a 400 is returned if none
/// are present.
public struct PostUpdateRequest: Encodable, Sendable {
    public var category: [String]?
    public var language: [String]?
    public var title: String?
    public var summary: String?
    public var reviewed: Bool?

    public init(category: [String]? = nil, language: [String]? = nil, title: String? = nil, summary: String? = nil, reviewed: Bool? = nil) {
        self.category = category
        self.language = language
        self.title = title
        self.summary = summary
        self.reviewed = reviewed
    }
}

public struct PostUpdateResponse: Codable, Sendable {
    public let success: Bool
    public let message: String
    public let shortcode: String
    public let updated_fields: [String]
}

public struct PostDeleteResponse: Codable, Sendable {
    public let success: Bool
    public let message: String
    public let shortcode: String
}

/// `POST /collections` upsert body.
public struct CollectionUpsertRequest: Encodable, Sendable {
    public let id: String
    public let name: String
    public let icon: String?
    public let post_ids: [String]
    public let created_at: String?
    public let updated_at: String?

    public init(id: String, name: String, icon: String?, post_ids: [String], created_at: String? = nil, updated_at: String? = nil) {
        self.id = id
        self.name = name
        self.icon = icon
        self.post_ids = post_ids
        self.created_at = created_at
        self.updated_at = updated_at
    }
}

/// `PUT /collections/{id}/posts` body.
public struct CollectionPostsUpdateRequest: Encodable, Sendable {
    public let post_ids: [String]

    public init(post_ids: [String]) {
        self.post_ids = post_ids
    }
}

/// `POST /chat/threads/{id}/messages` body.
public struct ChatMessageRequest: Encodable, Sendable {
    public let message: String

    public init(message: String) {
        self.message = message
    }
}

/// A minimal decode of `GET /recent`'s per-post shape — used only by the
/// Share Extension to look up a freshly-analyzed post's real shortcode by
/// URL, since `/analyze`'s response never includes it. Deliberately not the
/// full `Post` shape (LIGHT_COLUMNS has far more fields than needed here).
public struct RecentPostLookup: Decodable, Sendable {
    public let shortcode: String
    public let url: String
}

public struct RecentLookupResponse: Decodable, Sendable {
    public let success: Bool
    public let data: [RecentPostLookup]
}

/// `GET /caption?url=`'s response — a quick, uncached title/caption preview,
/// used by the Share Extension to show something more than a bare URL while
/// `/analyze` is still running.
public struct CaptionResponse: Codable, Sendable {
    public let success: Bool
    public let shortcode: String
    public let username: String
    public let title: String
    public let full_caption: String
    public let error: String?
}
