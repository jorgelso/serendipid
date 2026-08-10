import Foundation

/// Every non-2xx backend response is `{"detail": "<string>"}` (FastAPI's
/// default exception handler, `backend/api.py`) — there are no
/// machine-readable error codes, so this type exists to give call sites a
/// typed switch over the *status codes* that carry distinct meaning in this
/// API, while still carrying the raw message through for display.
public enum APIError: Error, LocalizedError, Sendable {
    case notConfigured
    case invalidURL
    case invalidResponse
    case network(String)
    case decoding(String)
    /// 400 — malformed request (e.g. an unrecognized URL passed to `/analyze`).
    case badRequest(String)
    /// 401 — bad or missing `X-API-Key`.
    case unauthorized(String)
    /// 403 — e.g. attempting to delete the default Watch Later collection.
    case forbidden(String)
    /// 404
    case notFound(String)
    /// 409 — `/analyze` called for a shortcode that's already mid-analysis.
    case alreadyProcessing(String)
    /// 503 — `/analyze`'s queue is full, or `/search/semantic` has no
    /// embedding provider configured server-side.
    case serviceUnavailable(String)
    /// 504 — `/analyze` exceeded the backend's 10-minute processing cap.
    case timeout(String)
    /// 202 from `/analyze` — non-standard: still an error-shaped `{"detail"}`
    /// body despite the 2xx status, meaning the request was queued for
    /// automatic retry after a quota/rate-limit exhaustion, not that analysis
    /// completed.
    case quotaQueuedForRetry(String)
    case serverError(status: Int, message: String)

    public var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "Connect to a SuperBrain server first, in Settings."
        case .invalidURL:
            return "That server address doesn't look like a valid URL."
        case .invalidResponse:
            return "The server sent back something unexpected."
        case .network(let message):
            return "Could not reach the SuperBrain backend — \(message)"
        case .decoding(let message):
            return "Could not understand the backend's response — \(message)"
        case .badRequest(let message),
             .unauthorized(let message),
             .forbidden(let message),
             .notFound(let message),
             .alreadyProcessing(let message),
             .serviceUnavailable(let message),
             .timeout(let message),
             .quotaQueuedForRetry(let message):
            return message
        case .serverError(let status, let message):
            return "Backend error \(status): \(message)"
        }
    }

    static func from(statusCode: Int, data: Data) -> APIError {
        let message = (try? JSONDecoder().decode(APIErrorBody.self, from: data))?.detail
            ?? String(data: data, encoding: .utf8).flatMap { $0.isEmpty ? nil : $0 }
            ?? "Unknown error"

        switch statusCode {
        case 400: return .badRequest(message)
        case 401: return .unauthorized("Backend rejected the API key — check the token in Settings.")
        case 403: return .forbidden(message)
        case 404: return .notFound(message)
        case 409: return .alreadyProcessing(message)
        case 503: return .serviceUnavailable(message)
        case 504: return .timeout(message)
        default: return .serverError(status: statusCode, message: message)
        }
    }

    /// Only network-level failures and generic 5xx are worth silently
    /// retrying — everything else (401/404/409/503/504/202) is a meaningful
    /// signal the caller needs to see, not a transient blip. Mirrors the
    /// Android app's `withRetry`, which likewise only wraps simple reads, not
    /// `/analyze`.
    var isRetryable: Bool {
        switch self {
        case .network: return true
        case .serverError(let status, _): return status >= 500
        default: return false
        }
    }
}
