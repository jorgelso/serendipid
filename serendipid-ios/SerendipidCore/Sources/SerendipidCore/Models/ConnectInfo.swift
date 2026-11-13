import Foundation

/// Mirrors `GET /connect-info`'s response (unauthenticated) — also the
/// payload shape a QR code should encode for the Settings screen's scan flow.
public struct ConnectInfo: Codable, Hashable, Sendable {
    public let url: String
    public let token: String
    public let version: String?
    public let name: String?
}

/// Every non-2xx response body from the backend (`FastAPI`'s default
/// exception handler) — always `{"detail": "<string>"}`, no machine-readable
/// error codes.
public struct APIErrorBody: Codable, Sendable {
    public let detail: String
}

/// `GET /ping` (unauthenticated liveness check).
public struct PingResponse: Codable, Sendable {
    public let status: String
    public let timestamp: String
}
