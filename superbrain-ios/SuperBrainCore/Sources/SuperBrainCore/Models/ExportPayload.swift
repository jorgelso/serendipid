import Foundation

/// Mirrors `GET /export?format=json`'s response — the single source of full
/// post/collection data for every screen (see `AppDataStore`).
public struct ExportPayload: Codable, Sendable {
    public let version: String
    public let exported_at: String
    public let posts: [Post]
    public let collections: [PostCollection]
    public let stats: [String: JSONValue]
}

/// Mirrors `GET /stats`'s `data` object.
public struct StatsResponse: Codable, Sendable {
    public let success: Bool
    public let data: [String: JSONValue]
}
