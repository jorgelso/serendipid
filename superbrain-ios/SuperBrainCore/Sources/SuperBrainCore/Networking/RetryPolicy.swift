import Foundation

/// Exponential backoff for transient failures — ports the Android app's
/// `withRetry` (`superbrain-app/src/services/api.ts`): max 2 retries, 1s base
/// delay doubling each attempt, only for errors `APIError.isRetryable` flags.
public struct RetryPolicy: Sendable {
    public let maxRetries: Int
    public let baseDelay: TimeInterval

    public init(maxRetries: Int = 2, baseDelay: TimeInterval = 1.0) {
        self.maxRetries = maxRetries
        self.baseDelay = baseDelay
    }

    public func run<T: Sendable>(_ operation: @Sendable () async throws -> T) async throws -> T {
        var attempt = 0
        while true {
            do {
                return try await operation()
            } catch {
                let retryable = (error as? APIError)?.isRetryable ?? false
                guard attempt < maxRetries, retryable else { throw error }
                let delaySeconds = baseDelay * pow(2.0, Double(attempt))
                try? await Task.sleep(nanoseconds: UInt64(delaySeconds * 1_000_000_000))
                attempt += 1
            }
        }
    }
}
