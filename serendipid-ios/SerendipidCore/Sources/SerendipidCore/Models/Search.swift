import Foundation

/// Mirrors `GET /search/semantic`'s per-hit shape — a narrower `Post` subset.
/// Missing fields (`visual_analysis`, `likes`, `post_date`, `media_urls`,
/// `language`, ...) are filled in by merging against the cached `/export`
/// payload on tap (see `AppDataStore.mergedPost(forHit:)`), mirroring the web
/// app's `mergeSearchHitsWithPosts`.
public struct SearchSemanticHit: Codable, Identifiable, Hashable, Sendable {
    public var id: String { shortcode }

    public let shortcode: String
    public let similarity: Double
    public let url: String
    public let username: String
    public let title: String
    public let summary: String
    public let tags: [String]
    public let category: [String]
    public let thumbnail: String
}

public struct SearchSemanticResponse: Codable, Sendable {
    public let success: Bool
    public let query: String
    public let count: Int
    public let data: [SearchSemanticHit]
}

/// Mirrors `GET /search?tags=&limit=`'s response — full `Post` objects.
public struct TagSearchResponse: Codable, Sendable {
    public let success: Bool
    public let tags: [String]
    public let count: Int
    public let data: [Post]
}

/// Mirrors `GET /category/{category}`'s response — full `Post` objects.
public struct CategoryPostsResponse: Codable, Sendable {
    public let success: Bool
    public let category: String
    public let count: Int
    public let data: [Post]
}
