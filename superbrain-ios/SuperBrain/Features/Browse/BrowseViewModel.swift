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

    enum SortOrder: String, CaseIterable {
        case recent = "Recent"
        case important = "Most important"
    }

    /// Mirrors the web app's eloquence filter (`EloquenceFilters.tsx`) — a
    /// content-delivery axis independent of topic/category.
    enum EloquenceFilter: String, CaseIterable {
        case eloquentOnly = "Eloquent"
        case tutorialOnly = "Tutorial-style"
        case speechOnly = "Speech/commentary"
    }

    var selectedCategory: String?
    var selectedLanguage: String?
    var selectedCollectionID: String?
    var selectedEloquenceFilter: EloquenceFilter?
    var sortOrder: SortOrder = .recent
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
        let filtered = allPosts.filter { post in
            if let selectedCategory, !post.category.contains(selectedCategory) { return false }
            if let selectedLanguage, !post.language.contains(selectedLanguage) { return false }
            if let selectedCollectionID,
               let collection = collections.first(where: { $0.id == selectedCollectionID }),
               !collection.post_ids.contains(post.shortcode) {
                return false
            }
            switch selectedEloquenceFilter {
            case nil:
                break
            case .eloquentOnly:
                if post.is_eloquent != 1 { return false }
            case .tutorialOnly:
                if post.is_eloquent != 1 || post.is_tutorial != 1 { return false }
            case .speechOnly:
                if post.is_eloquent != 1 || post.is_tutorial != 0 { return false }
            }
            return true
        }

        switch sortOrder {
        case .recent:
            return filtered
        case .important:
            return filtered.sorted { ($0.importance ?? 0) > ($1.importance ?? 0) }
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
        selectedEloquenceFilter = nil
        displayLimit = Self.pageSize
    }

    func onFilterChanged() {
        displayLimit = Self.pageSize
    }
}
