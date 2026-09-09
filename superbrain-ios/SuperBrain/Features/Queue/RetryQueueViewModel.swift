import Foundation
import SuperBrainCore

@MainActor
@Observable
final class RetryQueueViewModel {
    private let apiClient: APIClient
    private let pendingShareStore: PendingShareStore

    var loadState: LoadState = .idle
    var pendingShares: [PendingShare] = []
    var retryItems: [RetryQueueItem] = []
    var status: QueueStatusResponse?
    var isSyncing = false
    var isFlushing = false

    init(apiClient: APIClient, pendingShareStore: PendingShareStore = PendingShareStore()) {
        self.apiClient = apiClient
        self.pendingShareStore = pendingShareStore
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    func refresh() async {
        loadState = .loading
        pendingShares = pendingShareStore.pending().sorted { $0.createdAt > $1.createdAt }

        do {
            async let retryTask: RetryQueueResponse = apiClient.send(.retryQueue)
            async let statusTask: QueueStatusResponse = apiClient.send(.queueStatus)
            retryItems = try await retryTask.retry_queue
            status = try await statusTask
            loadState = .loaded
        } catch {
            // The local "waiting to send" list is still useful even if the
            // backend can't be reached right now to fetch its own retry queue.
            retryItems = []
            status = nil
            loadState = pendingShares.isEmpty ? .error(error.localizedDescription) : .loaded
        }
    }

    /// Cancels a share that never reached the backend — removes it from the
    /// local queue without ever sending it.
    func cancelPendingShare(_ share: PendingShare) {
        pendingShareStore.remove(id: share.id)
        pendingShares.removeAll { $0.id == share.id }
    }

    /// Attempts to send every locally-queued share right now, instead of
    /// waiting for the next app launch/foreground.
    func syncPendingSharesNow() async {
        guard !isSyncing else { return }
        isSyncing = true
        let syncer = PendingShareSyncer(apiClient: apiClient, store: pendingShareStore)
        await syncer.flush()
        isSyncing = false
        await refresh()
    }

    /// Force-promotes every retry-ready item on the backend to the active
    /// queue immediately, instead of waiting for its scheduled `retry_after`.
    func forceRetryAll() async {
        guard !isFlushing, !retryItems.isEmpty else { return }
        isFlushing = true
        let _: RetryFlushResponse? = try? await apiClient.send(.retryQueueFlush)
        isFlushing = false
        await refresh()
    }

    func deleteRetryItem(_ item: RetryQueueItem) async {
        retryItems.removeAll { $0.id == item.id }
        let _: QueueItemDeleteResponse? = try? await apiClient.send(.queueItemDelete(shortcode: item.shortcode))
    }
}
