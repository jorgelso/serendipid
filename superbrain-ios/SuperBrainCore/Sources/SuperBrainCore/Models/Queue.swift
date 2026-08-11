import Foundation

/// One row from `db.get_retry_queue()` — an item the backend already tried,
/// hit a quota/rate-limit exhaustion on, and scheduled for automatic retry
/// after `retry_after`. Surfaced in `RetryQueueView` so a "202 queued" isn't
/// a silent dead end.
public struct RetryQueueItem: Codable, Identifiable, Hashable, Sendable {
    public var id: String { shortcode }
    public let shortcode: String
    public let url: String
    public let content_type: String?
    public let reason: String?
    public let attempts: Int?
    public let retry_after: String?
    public let added_at: String?
}

public struct RetryQueueResponse: Codable, Sendable {
    public let retry_queue: [RetryQueueItem]
    public let count: Int
}

/// `GET /queue-status` — only the counts `RetryQueueView`'s summary header
/// needs; the full `queue`/`currently_processing` item lists are decoded
/// away automatically since `Decodable` ignores unlisted JSON keys.
public struct QueueStatusResponse: Codable, Sendable {
    public let processing_count: Int
    public let queue_count: Int
    public let retry_count: Int
    public let max_concurrent: Int?
    public let available_slots: Int?
}

public struct RetryFlushResponse: Codable, Sendable {
    public let flushed: Int
    public let items: [String]
}

public struct QueueItemDeleteResponse: Codable, Sendable {
    public let success: Bool
    public let message: String
}
