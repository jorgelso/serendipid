import Foundation

/// A share the Share Extension couldn't hand off to the backend at all
/// (`APIError.network` — offline, backend host unreachable, DNS failure),
/// as opposed to one the backend received and rejected/queued itself. Kept
/// in the App Group container so both the extension (which enqueues) and the
/// main app (which flushes, via `PendingShareSyncer`) see the same list.
///
/// Entries are never deleted once synced (`syncedAt` set instead) — this
/// doubles as a permanent record of every reel saved via the offline path,
/// not just an ephemeral retry queue. `remove(id:)` is reserved for a user
/// explicitly cancelling a share that was never sent at all.
public struct PendingShare: Codable, Identifiable, Hashable, Sendable {
    public let id: UUID
    public let url: String
    public let collectionID: String?
    public let createdAt: Date
    public var syncedAt: Date?

    public init(id: UUID = UUID(), url: String, collectionID: String?, createdAt: Date = Date(), syncedAt: Date? = nil) {
        self.id = id
        self.url = url
        self.collectionID = collectionID
        self.createdAt = createdAt
        self.syncedAt = syncedAt
    }
}

public final class PendingShareStore: @unchecked Sendable {
    /// Backend-seeded collection (`core/database.py`) every share that ever
    /// went through this offline queue is filed under, regardless of
    /// `collectionID` — it was shared straight from Instagram, never saved to
    /// a real Instagram collection first, so there's no folder to assign it
    /// to yet. `PendingShareSyncer` adds it here in addition to (never
    /// instead of) `collectionID`.
    public static let iPhoneCollectionID = "iphone_shares"

    private static let key = "serendipid.pendingShares"
    private let defaults: UserDefaults

    public init(suiteName: String = ServerConfigStore.appGroupSuiteName) {
        self.defaults = UserDefaults(suiteName: suiteName) ?? .standard
    }

    /// Not-yet-synced count — what the UI means by "waiting to send".
    public var count: Int { pending().count }

    /// Every share ever queued this way, synced or not — the permanent record.
    public func all() -> [PendingShare] {
        guard let data = defaults.data(forKey: Self.key) else { return [] }
        return (try? JSONDecoder().decode([PendingShare].self, from: data)) ?? []
    }

    /// Only shares still waiting to reach the backend.
    public func pending() -> [PendingShare] {
        all().filter { $0.syncedAt == nil }
    }

    @discardableResult
    public func enqueue(url: String, collectionID: String?) -> PendingShare {
        var items = all()
        let share = PendingShare(url: url, collectionID: collectionID)
        items.append(share)
        save(items)
        return share
    }

    /// Marks a share resolved (successfully sent, or dropped as unrecoverable)
    /// without deleting it — it stays in `all()` as history.
    public func markSynced(id: UUID) {
        var items = all()
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        items[index].syncedAt = Date()
        save(items)
    }

    /// Explicit user cancellation of a share that was never sent — the only
    /// path that actually deletes an entry.
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
