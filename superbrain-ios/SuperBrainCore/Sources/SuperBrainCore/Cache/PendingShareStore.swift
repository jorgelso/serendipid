import Foundation

/// A share the Share Extension couldn't hand off to the backend at all
/// (`APIError.network` — offline, backend host unreachable, DNS failure),
/// as opposed to one the backend received and rejected/queued itself. Kept
/// in the App Group container so both the extension (which enqueues) and the
/// main app (which flushes, via `PendingShareSyncer`) see the same list —
/// mirrors the Android app's offline-first save queue.
public struct PendingShare: Codable, Identifiable, Hashable, Sendable {
    public let id: UUID
    public let url: String
    public let collectionID: String?
    public let createdAt: Date

    public init(id: UUID = UUID(), url: String, collectionID: String?, createdAt: Date = Date()) {
        self.id = id
        self.url = url
        self.collectionID = collectionID
        self.createdAt = createdAt
    }
}

public final class PendingShareStore: @unchecked Sendable {
    private static let key = "superbrain.pendingShares"
    private let defaults: UserDefaults

    public init(suiteName: String = ServerConfigStore.appGroupSuiteName) {
        self.defaults = UserDefaults(suiteName: suiteName) ?? .standard
    }

    public var count: Int { all().count }

    public func all() -> [PendingShare] {
        guard let data = defaults.data(forKey: Self.key) else { return [] }
        return (try? JSONDecoder().decode([PendingShare].self, from: data)) ?? []
    }

    @discardableResult
    public func enqueue(url: String, collectionID: String?) -> PendingShare {
        var items = all()
        let share = PendingShare(url: url, collectionID: collectionID)
        items.append(share)
        save(items)
        return share
    }

    public func remove(id: UUID) {
        var items = all()
        items.removeAll { $0.id == id }
        save(items)
    }

    private func save(_ items: [PendingShare]) {
        guard let data = try? JSONEncoder().encode(items) else { return }
        defaults.set(data, forKey: Self.key)
    }
}
