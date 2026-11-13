import Foundation
import SerendipidCore

@MainActor
@Observable
final class SpaceViewModel {
    /// Below this, `VectorSpaceProjection` falls back to a ring layout
    /// rather than a real PCA projection — mirror that threshold here so the
    /// view can show explanatory copy instead of a not-very-meaningful scene.
    static let minPointsForMeaningfulLayout = 4

    /// Matches the web app's `/api/vector-space/search` route
    /// (`RESULT_LIMIT`/`MIN_SIMILARITY`) — same semantic-search endpoint the
    /// Search tab uses, just capped tighter and with a similarity floor so
    /// only genuinely related points light up.
    private static let searchResultLimit = 80
    private static let searchMinSimilarity = 0.15
    private static let searchDebounceNanoseconds: UInt64 = 350_000_000

    private let dataStore: AppDataStore
    private let configStore: ServerConfigStore
    private let apiClient: APIClient

    var loadState: LoadState = .idle
    var points: [VectorSpacePoint] = []
    var legendEntries: [(colorSlot: VectorSpaceColorSlot, label: String)] = []
    var baseURL: URL? { configStore.baseURL }

    /// Theme selection (legend) and text search both resolve to "a set of
    /// shortcodes to light up" and are mutually exclusive — starting one
    /// clears the other, mirroring the web app's `/space` page exactly
    /// (`legendSelection`/`searchShortcodes` in `VectorSpaceView.tsx`), so
    /// there's never an ambiguous "both active" state.
    private(set) var legendSelection: VectorSpaceColorSlot?
    var searchQuery: String = ""
    private(set) var searchResultShortcodes: Set<String>?
    private(set) var isSearching = false
    private(set) var searchError: String?
    private var searchTask: Task<Void, Never>?

    /// nil = show every point at full brightness. Non-nil = only points
    /// whose shortcode is in the set stay bright — everything else dims
    /// (handled in `SceneKitVectorSpaceView` via opacity, not by removing
    /// points from the scene, so spatial context is preserved).
    var highlightedShortcodes: Set<String>? {
        if let searchResultShortcodes { return searchResultShortcodes }
        guard let legendSelection else { return nil }
        return Set(points.filter { $0.colorSlot == legendSelection }.map(\.shortcode))
    }

    init(dataStore: AppDataStore, configStore: ServerConfigStore, apiClient: APIClient) {
        self.dataStore = dataStore
        self.configStore = configStore
        self.apiClient = apiClient
    }

    func toggleLegendSelection(_ slot: VectorSpaceColorSlot) {
        searchTask?.cancel()
        searchQuery = ""
        searchResultShortcodes = nil
        searchError = nil
        isSearching = false
        legendSelection = (legendSelection == slot) ? nil : slot
    }

    func clearHighlight() {
        searchTask?.cancel()
        searchQuery = ""
        searchResultShortcodes = nil
        searchError = nil
        isSearching = false
        legendSelection = nil
    }

    /// Called on every keystroke in the search field — debounces, cancels
    /// any in-flight request superseded by a newer one, and clears the
    /// legend selection the moment a real query starts (matches web's
    /// `handleSearchResults` clearing `legendSelection`).
    func onSearchQueryChanged() {
        searchTask?.cancel()
        legendSelection = nil

        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            searchResultShortcodes = nil
            searchError = nil
            isSearching = false
            return
        }

        searchTask = Task {
            try? await Task.sleep(nanoseconds: Self.searchDebounceNanoseconds)
            guard !Task.isCancelled else { return }
            await self.performSearch(query: query)
        }
    }

    private func performSearch(query: String) async {
        isSearching = true
        searchError = nil
        do {
            let response: SearchSemanticResponse = try await apiClient.send(
                .semanticSearch(query: query, limit: Self.searchResultLimit, minSimilarity: Self.searchMinSimilarity)
            )
            guard !Task.isCancelled else { return }
            searchResultShortcodes = Set(response.data.map(\.shortcode))
            isSearching = false
        } catch {
            guard !Task.isCancelled else { return }
            searchError = (error as? APIError)?.errorDescription ?? "Search failed."
            searchResultShortcodes = nil
            isSearching = false
        }
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    /// See `HomeViewModel.retryIfNeeded` — every tab-root screen retries a
    /// failed first load when the tab is reselected, since `.task` doesn't
    /// re-fire on its own.
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
            points = try await dataStore.getVectorSpace(forceRefresh: true)
            legendEntries = Self.buildLegend(points: points)
            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    /// One row per distinct theme actually represented in the scene, in
    /// slot order (theme-0, theme-1, ... then "other", then "unclustered").
    private static func buildLegend(points: [VectorSpacePoint]) -> [(colorSlot: VectorSpaceColorSlot, label: String)] {
        var seen: Set<VectorSpaceColorSlot> = []
        var entries: [(colorSlot: VectorSpaceColorSlot, label: String)] = []
        for point in points where !seen.contains(point.colorSlot) {
            seen.insert(point.colorSlot)
            entries.append((point.colorSlot, point.themeLabel))
        }
        return entries.sorted { lhs, rhs in
            Self.sortRank(lhs.colorSlot) < Self.sortRank(rhs.colorSlot)
        }
    }

    private static func sortRank(_ slot: VectorSpaceColorSlot) -> Int {
        switch slot {
        case .theme(let index): return index
        case .other: return 1000
        case .unclustered: return 1001
        }
    }
}
