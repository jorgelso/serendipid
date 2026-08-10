import Foundation
import UniformTypeIdentifiers
import SuperBrainCore

enum ShareState: Equatable {
    case notConfigured
    case loadingURL
    case ready(preview: String?)
    case saving
    case success
    case failure(String)
}

@MainActor
@Observable
final class ShareViewModel {
    private let configStore: ServerConfigStore
    private let apiClient: APIClient

    var state: ShareState = .loadingURL
    var sharedURL: String?
    var collections: [PostCollection] = []
    var selectedCollectionID: String?

    init() {
        let configStore = ServerConfigStore()
        self.configStore = configStore
        self.apiClient = APIClient(configStore: configStore)
    }

    func start(extensionContext: NSExtensionContext?) async {
        guard configStore.isConfigured else {
            state = .notConfigured
            return
        }

        guard let url = await Self.extractURL(from: extensionContext) else {
            state = .failure("Couldn't find a link to save in what was shared.")
            return
        }
        sharedURL = url

        async let captionTask: CaptionResponse? = try? apiClient.send(.caption(url: url))
        async let collectionsTask: PostCollectionsResponse? = try? apiClient.send(.collections)

        let caption = await captionTask
        collections = await collectionsTask?.data ?? []
        selectedCollectionID = configStore.defaultShareCollectionID

        state = .ready(preview: caption?.title.isEmpty == false ? caption?.title : nil)
    }

    func save(extensionContext: NSExtensionContext?) async {
        guard let sharedURL else { return }
        state = .saving

        do {
            let response: AnalysisResponse = try await apiClient.send(.analyze, body: AnalyzeRequest(url: sharedURL))
            guard response.success else {
                state = .failure(response.error ?? "Could not save this link.")
                return
            }

            if let selectedCollectionID,
               let collection = collections.first(where: { $0.id == selectedCollectionID }),
               let shortcode = await findShortcode(forURL: sharedURL) {
                var postIDs = collection.post_ids
                if !postIDs.contains(shortcode) {
                    postIDs.append(shortcode)
                    let _: PostCollectionResponse? = try? await apiClient.send(
                        .collectionPosts(id: selectedCollectionID),
                        body: CollectionPostsUpdateRequest(post_ids: postIDs)
                    )
                }
            }

            state = .success
            try? await Task.sleep(nanoseconds: 900_000_000)
            extensionContext?.completeRequest(returningItems: nil)
        } catch let error as APIError {
            switch error {
            case .alreadyProcessing:
                state = .failure("This link is already being analyzed.")
            case .serviceUnavailable(let message):
                state = .failure(message)
            case .quotaQueuedForRetry(let message):
                state = .failure(message)
            default:
                state = .failure(error.errorDescription ?? "Could not save this link.")
            }
        } catch {
            state = .failure(error.localizedDescription)
        }
    }

    func cancel(extensionContext: NSExtensionContext?) {
        extensionContext?.cancelRequest(withError: NSError(domain: "SuperBrain", code: -1))
    }

    /// `POST /analyze`'s response never includes the shortcode it computed
    /// (`AnalyzedPostSummary` has no such field) — rather than reimplementing
    /// the backend's per-content-type shortcode derivation (different rules
    /// for Instagram/YouTube/webpage — see `superbrain-app`'s
    /// `ShareHandlerScreen.buildShortcode()`), look the freshly-saved post up
    /// by URL in the most recent entries, which is robust to that algorithm
    /// changing later.
    private func findShortcode(forURL url: String) async -> String? {
        guard let response: RecentLookupResponse = try? await apiClient.send(.recent(limit: 5, offset: 0)) else { return nil }
        return response.data.first { $0.url == url }?.shortcode
    }

    private static func extractURL(from extensionContext: NSExtensionContext?) async -> String? {
        guard let items = extensionContext?.inputItems as? [NSExtensionItem] else { return nil }

        for item in items {
            guard let attachments = item.attachments else { continue }
            for provider in attachments {
                if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    if let url = await loadURL(provider) {
                        return url.absoluteString
                    }
                }
            }
        }

        for item in items {
            guard let attachments = item.attachments else { continue }
            for provider in attachments where provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                if let text = await loadText(provider), let url = firstURL(in: text) {
                    return url
                }
            }
        }

        return nil
    }

    private static func loadURL(_ provider: NSItemProvider) async -> URL? {
        await withCheckedContinuation { continuation in
            provider.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { item, _ in
                if let url = item as? URL {
                    continuation.resume(returning: url)
                } else if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(returning: nil)
                }
            }
        }
    }

    private static func loadText(_ provider: NSItemProvider) async -> String? {
        await withCheckedContinuation { continuation in
            provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { item, _ in
                continuation.resume(returning: item as? String)
            }
        }
    }

    private static func firstURL(in text: String) -> String? {
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        return detector.firstMatch(in: text, range: range).flatMap { $0.url?.absoluteString }
    }
}
