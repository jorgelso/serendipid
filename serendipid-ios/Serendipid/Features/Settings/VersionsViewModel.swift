import Foundation
import SerendipidCore

/// One row per stale `analysis_version` still present in the library —
/// how many posts, and the changelog entry (if any) for what changed at
/// that version.
struct StaleVersionGroup: Identifiable {
    var id: Int { version }
    let version: Int
    let shortcodes: [String]
    let entry: ChangelogEntry?
}

@MainActor
@Observable
final class VersionsViewModel {
    private let dataStore: AppDataStore
    private let apiClient: APIClient

    var loadState: LoadState = .idle
    var history: [ChangelogEntry] = []
    var currentVersion: Int?
    var staleGroups: [StaleVersionGroup] = []

    /// The version currently being bulk-rescanned, if any — only one at a
    /// time, mirroring the web app's `VersionPanel` busy state.
    var rescanningVersion: Int?
    var lastResult: BulkReanalyzeResponse?
    var errorMessage: String?

    init(dataStore: AppDataStore, apiClient: APIClient) {
        self.dataStore = dataStore
        self.apiClient = apiClient
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    func refresh() async {
        loadState = .loading
        do {
            let changelog = try await dataStore.getChangelog(forceRefresh: true)
            let export = try await dataStore.getExport()
            history = changelog.history
            currentVersion = changelog.current_version

            let grouped = Dictionary(grouping: export.posts, by: \.analysis_version)
            staleGroups = grouped
                .filter { version, _ in
                    if let currentVersion = changelog.current_version { return version < currentVersion }
                    return false
                }
                .map { version, posts in
                    StaleVersionGroup(
                        version: version,
                        shortcodes: posts.map(\.shortcode),
                        entry: changelog.history.first { $0.version == version }
                    )
                }
                .sorted { $0.version > $1.version }
            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    func rescan(_ group: StaleVersionGroup) async {
        rescanningVersion = group.version
        errorMessage = nil
        do {
            let response: BulkReanalyzeResponse = try await apiClient.send(
                .reanalyzeBulk,
                body: BulkReanalyzeRequest(shortcodes: group.shortcodes)
            )
            lastResult = response
            dataStore.invalidate()
            await refresh()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        rescanningVersion = nil
    }
}
