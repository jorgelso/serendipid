import Foundation
import SuperBrainCore

enum LoadState: Equatable {
    case idle
    case loading
    case loaded
    case error(String)
}

@MainActor
@Observable
final class HomeViewModel {
    private static let pageSize = 24

    private let dataStore: AppDataStore
    private let configStore: ServerConfigStore

    var loadState: LoadState = .idle
    var visiblePosts: [Post] = []
    /// "Recommended for you" rail — `RecommendationsEngine` ranked by
    /// similarity to a recency-weighted interest vector built from view
    /// history, falling back to top-importance recent posts when there's no
    /// view history yet. Mirrors the web app's Home recommendations rail.
    var recommendedPosts: [Post] = []
    var baseURL: URL? { configStore.baseURL }

    private var allPostsSortedByRecency: [Post] = []

    var hasMore: Bool { visiblePosts.count < allPostsSortedByRecency.count }

    init(dataStore: AppDataStore, configStore: ServerConfigStore) {
        self.dataStore = dataStore
        self.configStore = configStore
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    /// Called from `.onAppear` (unlike `.task`, this re-fires every time the
    /// tab is reselected) so a failed first load — most commonly "not
    /// connected yet" before the user has visited Settings — retries once
    /// they come back to this tab instead of staying stuck on the error
    /// state forever.
    func retryIfNeeded() async {
        switch loadState {
        case .loaded, .loading:
            return
        case .idle, .error:
            await refresh()
        }
    }

    func refresh() async {
        loadState = .loading
        do {
            let export = try await dataStore.getExport(forceRefresh: true)
            allPostsSortedByRecency = export.posts.sorted {
                ($0.analyzed_at ?? "") > ($1.analyzed_at ?? "")
            }
            visiblePosts = Array(allPostsSortedByRecency.prefix(Self.pageSize))
            loadState = .loaded

            let viewHistory = (try? await dataStore.getViewHistory()) ?? []
            let searchHistory = (try? await dataStore.getSearchHistory()) ?? []
            recommendedPosts = RecommendationsEngine.recommend(posts: export.posts, viewHistory: viewHistory, searchHistory: searchHistory)
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    func loadMore() {
        guard hasMore else { return }
        let nextCount = min(visiblePosts.count + Self.pageSize, allPostsSortedByRecency.count)
        visiblePosts = Array(allPostsSortedByRecency.prefix(nextCount))
    }
}
