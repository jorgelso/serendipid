import Foundation
import SuperBrainCore

@MainActor
@Observable
final class BrowseViewModel {
    private static let pageSize = 24

    private let dataStore: AppDataStore
    private let configStore: ServerConfigStore

    var loadState: LoadState = .idle
    var allPosts: [Post] = []
    var collections: [PostCollection] = []

    var selectedCategory: String?
    var selectedLanguage: String?
    var selectedCollectionID: String?
    var displayLimit = pageSize

    var baseURL: URL? { configStore.baseURL }

    init(dataStore: AppDataStore, configStore: ServerConfigStore) {
        self.dataStore = dataStore
        self.configStore = configStore
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    /// See `HomeViewModel.retryIfNeeded` — `.onAppear` fires every time this
    /// tab is reselected, unlike `.task`, so a failed first load (e.g. not
    /// connected yet) gets a chance to retry.
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
            let export = try await dataStore.getExport()
            allPosts = export.posts.sorted { ($0.analyzed_at ?? "") > ($1.analyzed_at ?? "") }
            collections = export.collections
            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    var categoryOptions: [String] {
        Array(Set(allPosts.flatMap(\.category))).sorted()
    }

    var languageOptions: [String] {
        Array(Set(allPosts.flatMap(\.language))).sorted()
    }

    var filteredPosts: [Post] {
        allPosts.filter { post in
            if let selectedCategory, !post.category.contains(selectedCategory) { return false }
            if let selectedLanguage, !post.language.contains(selectedLanguage) { return false }
            if let selectedCollectionID,
               let collection = collections.first(where: { $0.id == selectedCollectionID }),
               !collection.post_ids.contains(post.shortcode) {
                return false
            }
            return true
        }
    }

    var visiblePosts: [Post] {
        Array(filteredPosts.prefix(displayLimit))
    }

    var hasMore: Bool { displayLimit < filteredPosts.count }

    func loadMore() {
        displayLimit = min(displayLimit + Self.pageSize, filteredPosts.count)
    }

    func clearFilters() {
        selectedCategory = nil
        selectedLanguage = nil
        selectedCollectionID = nil
        displayLimit = Self.pageSize
    }

    func onFilterChanged() {
        displayLimit = Self.pageSize
    }
}
