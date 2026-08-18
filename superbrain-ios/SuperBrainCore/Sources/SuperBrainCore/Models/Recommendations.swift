import Foundation

/// One row of `GET /view-history` — a qualifying post view (video ≥60%
/// watched, or non-video open ≥20s), logged by `POST /post/{shortcode}/view`.
/// Feeds `RecommendationsEngine`'s interest vector, mirroring the web app's
/// `src/lib/recommendations.ts`.
public struct ViewHistoryEntry: Codable, Sendable {
    public let shortcode: String
    public let viewed_at: String
}

public struct ViewHistoryResponse: Codable, Sendable {
    public let success: Bool
    public let count: Int
    public let data: [ViewHistoryEntry]
}

public struct PostViewLogResponse: Codable, Sendable {
    public let success: Bool
    public let shortcode: String
}

/// One row of `GET /search-history` — every semantic-search query and chat
/// question, with its embedding (`search_queries` doubles as an embedding
/// cache server-side — see `backend/core/database.py`). `source`
/// distinguishes the Search tab / Space search bar (`"search"`) from Chat
/// (`"chat"`). Feeds `RecommendationsEngine` alongside view history, same
/// recency-weighting as the web app's `recommendations.ts`.
public struct SearchHistoryEntry: Codable, Sendable {
    public let query_text: String?
    public let query_embedding: [Float]?
    public let source: String?
    public let created_at: String
}

public struct SearchHistoryResponse: Codable, Sendable {
    public let success: Bool
    public let count: Int
    public let data: [SearchHistoryEntry]
}
