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

/// `PUT /post/{shortcode}` body — the backend only honors these 7 keys, all
/// optional; anything else is silently dropped, and a 400 is returned if none
/// are present. `enjoyment_rating`/`perceived_importance_rating` must each be
/// `nil`, `"liked"`, or `"loved"` — the backend 400s on anything else.
public struct PostUpdateRequest: Encodable, Sendable {
    public var category: [String]?
    public var language: [String]?
    public var title: String?
    public var summary: String?
    public var reviewed: Bool?
    public var enjoyment_rating: String??
    public var perceived_importance_rating: String??

    public init(
        category: [String]? = nil, language: [String]? = nil, title: String? = nil,
        summary: String? = nil, reviewed: Bool? = nil,
        enjoyment_rating: String?? = nil, perceived_importance_rating: String?? = nil
    ) {
        self.category = category
        self.language = language
        self.title = title
        self.summary = summary
        self.reviewed = reviewed
        self.enjoyment_rating = enjoyment_rating
        self.perceived_importance_rating = perceived_importance_rating
    }

    private enum CodingKeys: String, CodingKey {
        case category, language, title, summary, reviewed, enjoyment_rating, perceived_importance_rating
    }

    /// A double-optional (`String??`) is how "field explicitly set to null"
    /// (clear the rating) is distinguished from "field omitted" (leave it
    /// alone) — `Encodable`'s default synthesis can't express that
    /// distinction for an already-optional property, so encoding is manual.
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(category, forKey: .category)
        try container.encodeIfPresent(language, forKey: .language)
        try container.encodeIfPresent(title, forKey: .title)
        try container.encodeIfPresent(summary, forKey: .summary)
        try container.encodeIfPresent(reviewed, forKey: .reviewed)
        if let enjoyment_rating {
            try container.encode(enjoyment_rating, forKey: .enjoyment_rating)
        }
        if let perceived_importance_rating {
            try container.encode(perceived_importance_rating, forKey: .perceived_importance_rating)
        }
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
