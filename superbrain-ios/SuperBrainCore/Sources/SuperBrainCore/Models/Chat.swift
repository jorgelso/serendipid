import Foundation

/// Mirrors `backend/core/rag.py`'s `_light_source()` — the citation shape
/// attached to an assistant chat message. No `thumbnail` field: unlike the
/// web app (which proxies thumbnails through `/api/thumbnail/{shortcode}` to
/// avoid inlining huge base64 blobs into an HTML page), this app resolves the
/// thumbnail directly from its own already-cached `Post` by shortcode — no
/// proxy route is needed natively.
public struct ChatSource: Codable, Identifiable, Hashable, Sendable {
    public var id: String { shortcode }

    public let shortcode: String
    public let similarity: Double
    public let url: String
    public let username: String
    public let title: String
    public let summary: String
    public let tags: [String]
    /// Typed `string[] | string` even in the web app's own domain.ts — tolerant
    /// decode needed here, unlike `Post.category`.
    @FlexibleStringArray public var category: [String]

    enum CodingKeys: String, CodingKey {
        case shortcode, similarity, url, username, title, summary, tags, category
    }
}

public enum ChatRole: String, Codable, Hashable, Sendable {
    case user
    case assistant
}

/// Mirrors `backend/core/database.py`'s `chat_messages` table.
public struct ChatMessage: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let thread_id: String
    public let role: ChatRole
    public let content: String
    public let sources: [ChatSource]
    public let created_at: String
}

/// Mirrors `backend/core/database.py`'s `chat_threads` table.
public struct ChatThread: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String?
    public let created_at: String
    public let updated_at: String
}

/// `GET /chat/threads/{id}`'s response shape (thread + full message history).
public struct ChatThreadDetail: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String?
    public let created_at: String
    public let updated_at: String
    public let messages: [ChatMessage]
}

/// `POST /chat/threads/{id}/messages`'s response shape.
public struct ChatMessageExchange: Codable, Sendable {
    public let user_message: ChatMessage
    public let assistant_message: ChatMessage
}

public struct ChatThreadsResponse: Codable, Sendable {
    public let success: Bool
    public let count: Int
    public let data: [ChatThread]
}

public struct ChatThreadCreateResponse: Codable, Sendable {
    public let success: Bool
    public let data: ChatThread
}

public struct ChatThreadDetailResponse: Codable, Sendable {
    public let success: Bool
    public let data: ChatThreadDetail
}

public struct ChatMessageExchangeResponse: Codable, Sendable {
    public let success: Bool
    public let data: ChatMessageExchange
}

public struct ChatThreadDeleteResponse: Codable, Sendable {
    public let success: Bool
}
