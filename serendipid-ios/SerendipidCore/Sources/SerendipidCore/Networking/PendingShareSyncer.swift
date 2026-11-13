import Foundation

/// Drains `PendingShareStore` against the live backend — called on app
/// launch and foreground (`RootTabView`) and from the manual "Sync now"
/// action in `RetryQueueView`. One pass, one attempt per not-yet-synced item;
/// each item's outcome decides whether it stays queued for the next pass:
///
/// - success → applied (collection membership too) and marked synced.
/// - `.network` (still unreachable) or `.unauthorized`/`.forbidden`/
///   `.notConfigured` (a config problem, not a per-item one) → stop the pass
///   entirely; every remaining item stays queued untouched.
/// - `.alreadyProcessing` (backend's already on it) or `.quotaQueuedForRetry`
///   (backend accepted it into *its own* retry queue — now visible in
///   `RetryQueueView`) or `.badRequest` (unrecoverable) → marked synced
///   (nothing more for this client to do), never retried again.
/// - anything else (5xx, decoding, timeout) → transient; leave queued, keep
///   going with the rest of the pass.
///
/// Marking synced (`PendingShareStore.markSynced`) never deletes the entry —
/// `store.all()` stays a permanent, ever-growing record of every reel shared
/// this way, exactly like `import_saved_instagram.py`'s resumable state file
/// on the backend: safe to keep replaying, since a cache hit on an
/// already-analyzed shortcode just returns instantly.
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
        for share in store.pending() {
            do {
                let response: AnalysisResponse = try await apiClient.send(
                    .analyze,
                    body: AnalyzeRequest(url: share.url, restore: true)
                )
                if response.success {
                    await applyCollections(for: share)
                }
                store.markSynced(id: share.id)
                syncedCount += 1
            } catch let error as APIError {
                switch error {
                case .network, .unauthorized, .forbidden, .notConfigured:
                    return syncedCount
                case .alreadyProcessing, .quotaQueuedForRetry, .badRequest:
                    store.markSynced(id: share.id)
                default:
                    continue
                }
            } catch {
                continue
            }
        }
        return syncedCount
    }

    /// Files the shortcode into `PendingShareStore.iPhoneCollectionID` (always
    /// — this share never went through Instagram's own "saved to collection"
    /// flow) and, if the user had one selected, `share.collectionID` too.
    /// Additive only, on both: a later real Instagram export import that
    /// finds this post in a real folder just adds that folder as well —
    /// nothing here ever removes it from either collection.
    private func applyCollections(for share: PendingShare) async {
        guard let recent: RecentLookupResponse = try? await apiClient.send(.recent(limit: 5, offset: 0)),
              let shortcode = recent.data.first(where: { $0.url == share.url })?.shortcode
        else { return }
        guard let collections: PostCollectionsResponse = try? await apiClient.send(.collections) else { return }

        var targetIDs = [PendingShareStore.iPhoneCollectionID]
        if let collectionID = share.collectionID, collectionID != PendingShareStore.iPhoneCollectionID {
            targetIDs.append(collectionID)
        }

        for collectionID in targetIDs {
            guard let collection = collections.data.first(where: { $0.id == collectionID }) else { continue }
            var postIDs = collection.post_ids
            guard !postIDs.contains(shortcode) else { continue }
            postIDs.append(shortcode)
            let _: PostCollectionResponse? = try? await apiClient.send(
                .collectionPosts(id: collectionID),
                body: CollectionPostsUpdateRequest(post_ids: postIDs)
            )
        }
    }
}
