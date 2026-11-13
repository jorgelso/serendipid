import Foundation

/// Mirrors `backend/core/database.py`'s `analysis_changelog` table.
public struct ChangelogEntry: Codable, Identifiable, Hashable, Sendable {
    public var id: Int { version }

    public let version: Int
    public let released_at: String?
    public let title: String
    public let description: String
}

/// Mirrors `GET /changelog`'s response — newest version first.
public struct ChangelogResponse: Codable, Sendable {
    public let success: Bool
    public let current_version: Int?
    public let history: [ChangelogEntry]
}
