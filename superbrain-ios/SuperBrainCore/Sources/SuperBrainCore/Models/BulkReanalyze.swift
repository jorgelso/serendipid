import Foundation

/// `POST /reanalyze/bulk` body — rescans every listed shortcode, used to
/// bring a whole stale `analysis_version` cohort up to date at once (see
/// `VersionsView`).
public struct BulkReanalyzeRequest: Encodable, Sendable {
    public let shortcodes: [String]

    public init(shortcodes: [String]) {
        self.shortcodes = shortcodes
    }
}

public struct BulkReanalyzeError: Codable, Sendable {
    public let shortcode: String
    public let error: String
}

/// `rescored` = cheap importance-only fix applied synchronously (posts that
/// were exactly at version 7). `queued` = hard-deleted and queued for a full
/// re-analysis by the background queue worker (async — check `/queue-status`
/// for progress).
public struct BulkReanalyzeResponse: Codable, Sendable {
    public let success: Bool
    public let rescored: [String]
    public let queued: [String]
    public let errors: [BulkReanalyzeError]
}
