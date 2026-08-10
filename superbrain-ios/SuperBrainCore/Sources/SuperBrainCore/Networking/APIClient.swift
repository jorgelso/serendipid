import Foundation

/// URLSession-based, async/await backend client. Attaches `X-API-Key` from
/// `ServerConfigStore` to every authenticated request, retries transient
/// failures per `RetryPolicy`/`APIError.isRetryable`, and maps non-2xx
/// responses to typed `APIError` cases via `APIEndpoint`'s route table.
///
/// An `actor` (not `@MainActor`) so both the main app and the Share Extension
/// — which have no reason to run on the main thread — can call it directly
/// off any context.
public actor APIClient {
    private let configStore: ServerConfigStore
    private let session: URLSession
    private let retryPolicy: RetryPolicy
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(configStore: ServerConfigStore, session: URLSession = .shared, retryPolicy: RetryPolicy = RetryPolicy()) {
        self.configStore = configStore
        self.session = session
        self.retryPolicy = retryPolicy
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    /// GET-shaped calls, or any call with no request body.
    public func send<T: Decodable & Sendable>(_ endpoint: APIEndpoint) async throws -> T {
        try await performWithRetry(endpoint, bodyData: nil)
    }

    /// POST/PUT calls with an `Encodable` body.
    public func send<Body: Encodable, T: Decodable & Sendable>(_ endpoint: APIEndpoint, body: Body) async throws -> T {
        let bodyData = try encoder.encode(body)
        return try await performWithRetry(endpoint, bodyData: bodyData)
    }

    private func performWithRetry<T: Decodable & Sendable>(_ endpoint: APIEndpoint, bodyData: Data?) async throws -> T {
        if endpoint.isRetryable {
            return try await retryPolicy.run { [self] in
                try await self.performRequest(endpoint, bodyData: bodyData)
            }
        }
        return try await performRequest(endpoint, bodyData: bodyData)
    }

    private func performRequest<T: Decodable>(_ endpoint: APIEndpoint, bodyData: Data?) async throws -> T {
        guard let baseURL = configStore.baseURL else {
            throw APIError.notConfigured
        }
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(endpoint.path),
            resolvingAgainstBaseURL: false
        ) else {
            throw APIError.invalidURL
        }
        if !endpoint.queryItems.isEmpty {
            components.queryItems = endpoint.queryItems
        }
        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url, timeoutInterval: endpoint.timeout)
        request.httpMethod = endpoint.method.rawValue

        if endpoint.requiresAuth {
            guard let token = configStore.apiToken, !token.isEmpty else {
                throw APIError.notConfigured
            }
            request.setValue(token, forHTTPHeaderField: "X-API-Key")
        }

        if let bodyData {
            request.httpBody = bodyData
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        // 202 from /analyze is a non-standard "queued for retry" error body
        // despite the 2xx status — must be special-cased before the generic
        // success-range check below.
        if http.statusCode == 202 {
            let message = (try? decoder.decode(APIErrorBody.self, from: data))?.detail
                ?? "Rate limit or quota exhausted — queued for automatic retry."
            throw APIError.quotaQueuedForRetry(message)
        }

        guard (200..<300).contains(http.statusCode) else {
            throw APIError.from(statusCode: http.statusCode, data: data)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }
}
