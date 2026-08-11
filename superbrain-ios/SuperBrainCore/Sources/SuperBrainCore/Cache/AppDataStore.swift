import Foundation
import Observation

/// Light in-memory cache for the whole app — ports
/// `superbrain-web/src/lib/cache.ts`'s contract exactly: fetch-per-screen,
/// no offline-first local database. `getExport()` is the single source every
/// screen (Home, Browse, Search-merge, Post Detail, Insights) reads from,
/// since there is no `GET /post/{shortcode}` — a full post lookup is always a
/// shortcode search through this cached payload. `invalidate()` mirrors the
/// web app's `invalidateCache()`, called after any mutation (edit, reanalyze,
/// mark-reviewed) so the next screen visit refetches.
@MainActor
@Observable
public final class AppDataStore {
    private let client: APIClient

    public private(set) var exportPayload: ExportPayload?
    public private(set) var exportFetchedAt: Date?
    public private(set) var themes: [Theme]?
    public private(set) var unclusteredShortcodes: [String]?
    public private(set) var vectorSpacePoints: [VectorSpacePoint]?
    public private(set) var changelog: ChangelogResponse?

    /// Guards against duplicate concurrent fetches (e.g. two screens opening
    /// at once both calling `getExport()`).
    private var inFlightExport: Task<ExportPayload, Error>?

    public init(client: APIClient) {
        self.client = client
    }

    @discardableResult
    public func getExport(forceRefresh: Bool = false) async throws -> ExportPayload {
        if !forceRefresh, let cached = exportPayload {
            return cached
        }
        if let inFlight = inFlightExport {
            return try await inFlight.value
        }

        let task = Task<ExportPayload, Error> {
            try await client.send(.export())
        }
        inFlightExport = task

        do {
            let payload = try await task.value
            exportPayload = payload
            exportFetchedAt = Date()
            themes = nil
            unclusteredShortcodes = nil
            vectorSpacePoints = nil
            inFlightExport = nil
            return payload
        } catch {
            inFlightExport = nil
            throw error
        }
    }

    @discardableResult
    public func getThemes(forceRefresh: Bool = false) async throws -> (themes: [Theme], unclustered: [String]) {
        if !forceRefresh, let themes, let unclusteredShortcodes {
            return (themes, unclusteredShortcodes)
        }
        let payload = try await getExport()
        guard FeatureFlags.clusteringEnabled else {
            return ([], payload.posts.map(\.shortcode))
        }
        // O(n²) over embeddings — a few seconds even on a fast machine for a
        // few hundred posts, and much slower in an unoptimized debug build.
        // Run off the main actor so this doesn't freeze the UI; AppDataStore
        // itself is @MainActor, so the heavy work has to happen in a
        // detached task, not inline here.
        let posts = payload.posts
        let result = await Task.detached(priority: .userInitiated) {
            ThemeClustering.computeThemes(posts: posts)
        }.value
        themes = result.themes
        unclusteredShortcodes = result.unclusteredShortcodes
        return (result.themes, result.unclusteredShortcodes)
    }

    /// Positions every post in the Space tab's 3D scene via dual PCA over
    /// embeddings, colored by `getThemes()`'s clusters — never re-clusters.
    /// Same off-main-actor shape as `getThemes()`: PCA's Gram-matrix power
    /// iteration is real CPU work (an N×N matrix over up to a few hundred
    /// posts), so it runs in a detached task rather than blocking this
    /// `@MainActor` class's synchronous callers.
    @discardableResult
    public func getVectorSpace(forceRefresh: Bool = false) async throws -> [VectorSpacePoint] {
        if !forceRefresh, let vectorSpacePoints {
            return vectorSpacePoints
        }
        let themeResult = try await getThemes(forceRefresh: forceRefresh)
        let posts = try await getExport().posts
        let points = await Task.detached(priority: .userInitiated) {
            VectorSpaceProjection.compute(posts: posts, themes: themeResult.themes)
        }.value
        vectorSpacePoints = points
        return points
    }

    @discardableResult
    public func getChangelog(forceRefresh: Bool = false) async throws -> ChangelogResponse {
        if !forceRefresh, let changelog {
            return changelog
        }
        let response: ChangelogResponse = try await client.send(.changelog)
        changelog = response
        return response
    }

    /// Synchronous shortcode lookup into whatever's currently cached — does
    /// not fetch. Callers should `getExport(forceRefresh: true)` once and
    /// retry if this returns nil (e.g. a just-shared post not yet cached).
    public func post(shortcode: String) -> Post? {
        exportPayload?.posts.first { $0.shortcode == shortcode }
    }

    public func collections() -> [PostCollection] {
        exportPayload?.collections ?? []
    }

    /// Mirrors `cache.ts`'s `invalidateCache()`: clears export + derived
    /// themes, deliberately leaves `changelog` alone (it isn't touched by any
    /// post mutation).
    public func invalidate() {
        exportPayload = nil
        exportFetchedAt = nil
        themes = nil
        unclusteredShortcodes = nil
        vectorSpacePoints = nil
    }
}
