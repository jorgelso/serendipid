import Foundation
import SuperBrainCore

@MainActor
@Observable
final class SearchViewModel {
    private let apiClient: APIClient
    private let dataStore: AppDataStore
    private let configStore: ServerConfigStore

    var query: String = ""
    var loadState: LoadState = .idle
    var hits: [SearchSemanticHit] = []

    var baseURL: URL? { configStore.baseURL }

    private var searchTask: Task<Void, Never>?

    init(apiClient: APIClient, dataStore: AppDataStore, configStore: ServerConfigStore) {
        self.apiClient = apiClient
        self.dataStore = dataStore
        self.configStore = configStore
    }

    func onQueryChanged() {
        searchTask?.cancel()
        let currentQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !currentQuery.isEmpty else {
            hits = []
            loadState = .idle
            return
        }
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            await self.performSearch(query: currentQuery)
        }
    }

    /// Re-runs the current query — used by the results list's pull-to-refresh,
    /// since a plain re-fetch (unlike `onQueryChanged`) shouldn't debounce.
    func refresh() async {
        let currentQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !currentQuery.isEmpty else { return }
        await performSearch(query: currentQuery)
    }

    private func performSearch(query: String) async {
        loadState = .loading
        do {
            let response: SearchSemanticResponse = try await apiClient.send(
                .semanticSearch(query: query, limit: 24, minSimilarity: 0)
            )
            guard !Task.isCancelled else { return }
            hits = response.data
            loadState = .loaded
        } catch {
            guard !Task.isCancelled else { return }
            loadState = .error(error.localizedDescription)
        }
    }

    /// Merges a search hit with the fuller cached `/export` record for the
    /// same shortcode, filling in fields `/search/semantic` omits — mirrors
    /// the web app's `mergeSearchHitsWithPosts`.
    func mergedPost(for hit: SearchSemanticHit) -> Post {
        if let full = dataStore.post(shortcode: hit.shortcode) {
            return full
        }
        return Post(
            shortcode: hit.shortcode, url: hit.url, username: hit.username, content_type: "instagram",
            analyzed_at: nil, updated_at: nil, post_date: nil, likes: nil, importance: nil,
            thumbnail: hit.thumbnail, title: hit.title, summary: hit.summary, tags: hit.tags,
            music: nil, category: hit.category, language: [], visual_analysis: nil,
            audio_transcription: nil, text_analysis: nil, is_hidden: 0, source_hashtags: [],
            media_files: [], media_urls: [], analysis_version: 0, needs_review: false, embedding: nil
        )
    }
}
