import Foundation
import SuperBrainCore

@MainActor
@Observable
final class PostDetailViewModel {
    let shortcode: String
    private let dataStore: AppDataStore
    private let configStore: ServerConfigStore

    var post: Post?
    var loadState: LoadState = .idle
    var relatedPosts: [RelatedPost] = []

    var baseURL: URL? { configStore.baseURL }

    init(shortcode: String, dataStore: AppDataStore, configStore: ServerConfigStore) {
        self.shortcode = shortcode
        self.dataStore = dataStore
        self.configStore = configStore
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await load()
    }

    func load() async {
        loadState = .loading

        if let cached = dataStore.post(shortcode: shortcode) {
            apply(post: cached)
            return
        }

        do {
            let export = try await dataStore.getExport(forceRefresh: true)
            guard let found = export.posts.first(where: { $0.shortcode == shortcode }) else {
                loadState = .error("This post couldn't be found — it may have been deleted.")
                return
            }
            apply(post: found)
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    private func apply(post: Post) {
        self.post = post
        self.loadState = .loaded
        if let allPosts = dataStore.exportPayload?.posts {
            self.relatedPosts = RelatedPosts.find(for: post, in: allPosts, limit: 8)
        }
    }

    /// Called after a successful edit/reanalyze/mark-reviewed mutation —
    /// invalidates the shared cache and reloads this post from a fresh
    /// export, mirroring the web app's `invalidateCache()` + refresh flow.
    func reload() async {
        dataStore.invalidate()
        loadState = .idle
        await load()
    }
}
