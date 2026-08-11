import Foundation

public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
}

/// One case per backend route this app calls (`backend/api.py`). Centralizing
/// path/method/query construction here means a route change is a one-file
/// update.
public enum APIEndpoint: Sendable {
    case export(limit: Int = 50000, offset: Int = 0)
    /// Only used by the Share Extension to look up a freshly-analyzed post's
    /// real shortcode by URL (`/analyze`'s response never includes it) —
    /// every other screen reads from the cached `/export` payload instead.
    case recent(limit: Int = 5, offset: Int = 0)
    case categoryPosts(category: String, limit: Int = 100)
    case tagSearch(tags: [String], limit: Int = 100)
    case semanticSearch(query: String, limit: Int = 24, minSimilarity: Double = 0)
    case categories
    case stats
    case changelog
    case collections
    case collectionUpsert
    case collectionPosts(id: String)
    case collectionDelete(id: String)
    case chatThreads
    case chatThreadCreate
    case chatThread(id: String)
    case chatThreadDelete(id: String)
    case chatMessages(threadID: String)
    case postUpdate(shortcode: String)
    case postDelete(shortcode: String)
    case analyze
    case caption(url: String)
    case ping
    case connectInfo
    /// Counts of what's currently processing/queued/awaiting retry
    /// (`backend/api.py`'s `/queue-status`) — used by `RetryQueueView` for
    /// the summary header.
    case queueStatus
    /// Items the backend already gave up on after a quota/rate-limit
    /// exhaustion and scheduled for automatic retry (`/queue/retry`) —
    /// distinct from `PendingShareStore`'s *local* queue, which is for
    /// shares that never reached the backend at all.
    case retryQueue
    /// Force-promotes every retry-ready item to the active processing queue
    /// immediately, instead of waiting for its scheduled `retry_after`.
    case retryQueueFlush
    case queueItemDelete(shortcode: String)

    public var method: HTTPMethod {
        switch self {
        case .export, .recent, .categoryPosts, .tagSearch, .semanticSearch, .categories, .stats,
             .changelog, .collections, .chatThreads, .chatThread, .caption, .ping, .connectInfo,
             .queueStatus, .retryQueue:
            return .get
        case .collectionUpsert, .chatThreadCreate, .chatMessages, .analyze, .retryQueueFlush:
            return .post
        case .postUpdate, .collectionPosts:
            return .put
        case .postDelete, .collectionDelete, .chatThreadDelete, .queueItemDelete:
            return .delete
        }
    }

    public var path: String {
        switch self {
        case .export: return "/export"
        case .recent: return "/recent"
        case .categoryPosts(let category, _): return "/category/\(category)"
        case .tagSearch: return "/search"
        case .semanticSearch: return "/search/semantic"
        case .categories: return "/categories"
        case .stats: return "/stats"
        case .changelog: return "/changelog"
        case .collections, .collectionUpsert: return "/collections"
        case .collectionPosts(let id): return "/collections/\(id)/posts"
        case .collectionDelete(let id): return "/collections/\(id)"
        case .chatThreads, .chatThreadCreate: return "/chat/threads"
        case .chatThread(let id), .chatThreadDelete(let id): return "/chat/threads/\(id)"
        case .chatMessages(let threadID): return "/chat/threads/\(threadID)/messages"
        case .postUpdate(let shortcode), .postDelete(let shortcode): return "/post/\(shortcode)"
        case .analyze: return "/analyze"
        case .caption: return "/caption"
        case .ping: return "/ping"
        case .connectInfo: return "/connect-info"
        case .queueStatus: return "/queue-status"
        case .retryQueue: return "/queue/retry"
        case .retryQueueFlush: return "/queue/retry/flush"
        case .queueItemDelete(let shortcode): return "/queue/\(shortcode)"
        }
    }

    public var queryItems: [URLQueryItem] {
        switch self {
        case .export(let limit, let offset):
            return [.init(name: "limit", value: "\(limit)"), .init(name: "offset", value: "\(offset)"), .init(name: "format", value: "json")]
        case .recent(let limit, let offset):
            return [.init(name: "limit", value: "\(limit)"), .init(name: "offset", value: "\(offset)")]
        case .categoryPosts(_, let limit):
            return [.init(name: "limit", value: "\(limit)")]
        case .tagSearch(let tags, let limit):
            return [.init(name: "tags", value: tags.joined(separator: ",")), .init(name: "limit", value: "\(limit)")]
        case .semanticSearch(let query, let limit, let minSimilarity):
            return [
                .init(name: "q", value: query),
                .init(name: "limit", value: "\(limit)"),
                .init(name: "min_similarity", value: "\(minSimilarity)"),
            ]
        case .caption(let url):
            return [.init(name: "url", value: url)]
        default:
            return []
        }
    }

    /// Every route requires `X-API-Key` except these three (`backend/api.py`'s
    /// `verify_token` isn't in their dependency list).
    public var requiresAuth: Bool {
        switch self {
        case .ping, .connectInfo: return false
        default: return true
        }
    }

    /// `/analyze` runs the full AI pipeline (or spawns `main.py` as a
    /// subprocess for Instagram posts) — 60s, not the default 10s.
    public var timeout: TimeInterval {
        switch self {
        case .analyze: return 60
        default: return 10
        }
    }

    /// See `APIError.isRetryable` — `/analyze`'s 202/409/503/504 are
    /// meaningful signals the caller must see, not something to silently
    /// retry underneath them.
    public var isRetryable: Bool {
        switch self {
        case .analyze: return false
        default: return true
        }
    }
}
