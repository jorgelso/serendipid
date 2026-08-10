import Foundation

/// Mirrors the backend's `collections` table (`backend/core/database.py`).
/// Named `PostCollection`, not `Collection`, to avoid colliding with Swift's
/// standard library `Collection` protocol. The seeded `"default_watch_later"`
/// row cannot be deleted via the API (403).
public struct PostCollection: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let icon: String?
    /// `/collections` returns a real JSON array; `/export`'s embedded
    /// collections return this same column JSON-text-encoded as a *string*
    /// instead — see `FlexibleStringArray` for why this needs the tolerant
    /// decoder rather than plain `[String]`.
    @FlexibleStringArray public var post_ids: [String]
    public let created_at: String
    public let updated_at: String

    enum CodingKeys: String, CodingKey {
        case id, name, icon, post_ids, created_at, updated_at
    }

    public init(id: String, name: String, icon: String?, post_ids: [String], created_at: String, updated_at: String) {
        self.id = id
        self.name = name
        self.icon = icon
        self._post_ids = FlexibleStringArray(wrappedValue: post_ids)
        self.created_at = created_at
        self.updated_at = updated_at
    }
}

public struct PostCollectionsResponse: Codable, Sendable {
    public let success: Bool
    public let data: [PostCollection]
}

public struct PostCollectionResponse: Codable, Sendable {
    public let success: Bool
    public let data: PostCollection
}
