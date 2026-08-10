import Foundation
import SuperBrainCore

@MainActor
@Observable
final class InsightsViewModel {
    private let dataStore: AppDataStore

    var loadState: LoadState = .idle
    var totalPosts = 0
    var needsReviewCount = 0
    var categoryCounts: [(label: String, count: Int)] = []
    var languageCounts: [(label: String, count: Int)] = []
    var tagCounts: [(label: String, count: Int)] = []
    var themes: [Theme] = []

    init(dataStore: AppDataStore) {
        self.dataStore = dataStore
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    /// See `HomeViewModel.retryIfNeeded`.
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
            let posts = export.posts

            totalPosts = posts.count
            needsReviewCount = posts.filter(\.needs_review).count
            categoryCounts = Self.countLabels(posts.map(\.category), fallback: "Uncategorized")
            languageCounts = Self.countLabels(posts.map(\.language), fallback: "Unknown")
            tagCounts = Array(Self.countLabels(posts.map(\.tags), fallback: nil).prefix(20))

            if FeatureFlags.clusteringEnabled {
                let result = try await dataStore.getThemes()
                themes = result.themes
            } else {
                themes = []
            }

            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    private static func countLabels(_ groups: [[String]], fallback: String?) -> [(label: String, count: Int)] {
        var counts: [String: Int] = [:]
        for group in groups {
            if group.isEmpty, let fallback {
                counts[fallback, default: 0] += 1
            }
            for label in group {
                counts[label, default: 0] += 1
            }
        }
        return counts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
    }
}
