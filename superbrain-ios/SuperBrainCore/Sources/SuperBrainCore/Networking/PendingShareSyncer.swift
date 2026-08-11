import Foundation

/// Drains `PendingShareStore` against the live backend — called on app
/// launch and foreground (`RootTabView`) and from the manual "Sync now"
/// action in `RetryQueueView`. One pass, one attempt per item; each item's
/// outcome decides whether it stays queued for the next pass:
///
/// - success → applied (collection membership too, if any) and removed.
/// - `.network` (still unreachable) or `.unauthorized`/`.forbidden`/
///   `.notConfigured` (a config problem, not a per-item one) → stop the pass
///   entirely; every remaining item stays queued untouched.
/// - `.alreadyProcessing` (backend's already on it) or `.quotaQueuedForRetry`
///   (backend accepted it into *its own* retry queue — now visible in
///   `RetryQueueView`) or `.badRequest` (unrecoverable) → drop locally,
///   nothing more for this client to do.
/// - anything else (5xx, decoding, timeout) → transient; leave queued, keep
///   going with the rest of the pass.
public actor PendingShareSyncer {
    private let apiClient: APIClient
    private let store: PendingShareStore

    public init(apiClient: APIClient, store: PendingShareStore) {
        self.apiClient = apiClient
        self.store = store
    }

    @discardableResult
    public func flush() async -> Int {
        var syncedCount = 0
        for share in store.all() {
            do {
                let response: AnalysisResponse = try await apiClient.send(
                    .analyze,
                    body: AnalyzeRequest(url: share.url, restore: true)
                )
                if response.success {
                    await applyCollection(for: share)
                }
                store.remove(id: share.id)
                syncedCount += 1
            } catch let error as APIError {
                switch error {
                case .network, .unauthorized, .forbidden, .notConfigured:
                    return syncedCount
                case .alreadyProcessing, .quotaQueuedForRetry, .badRequest:
                    store.remove(id: share.id)
                default:
                    continue
                }
            } catch {
                continue
            }
        }
        return syncedCount
    }

    /// Mirrors `ShareViewModel.findShortcode(forURL:)` — `/analyze`'s
    /// response never includes the shortcode it computed.
    private func applyCollection(for share: PendingShare) async {
        guard let collectionID = share.collectionID else { return }
        guard let recent: RecentLookupResponse = try? await apiClient.send(.recent(limit: 5, offset: 0)),
              let shortcode = recent.data.first(where: { $0.url == share.url })?.shortcode
        else { return }
        guard let collections: PostCollectionsResponse = try? await apiClient.send(.collections),
              let collection = collections.data.first(where: { $0.id == collectionID })
        else { return }

        var postIDs = collection.post_ids
        guard !postIDs.contains(shortcode) else { return }
        postIDs.append(shortcode)
        let _: PostCollectionResponse? = try? await apiClient.send(
            .collectionPosts(id: collectionID),
            body: CollectionPostsUpdateRequest(post_ids: postIDs)
        )
    }
}
