import Foundation

/// Ports the spirit of `superbrain-web/src/lib/recommendations.ts`'s hybrid
/// mode: build an "interest vector" from recently-viewed posts' embeddings
/// AND recent search/chat query embeddings (both recency-weighted, same
/// half-life and relative weights as the web engine), then rank every other
/// post by cosine similarity to it. Deliberately a single blended strategy
/// rather than the web app's switchable "by theme / by similarity / hybrid"
/// — a native port of all three plus their UI toggle isn't worth the
/// complexity for what's an auxiliary Home-screen rail, not a primary
/// surface.
public enum RecommendationsEngine {
    /// Matches `recommendations.ts`'s `RECENCY_HALF_LIFE_DAYS` — a view or
    /// search from 30 days ago counts for about half of one from today.
    private static let recencyHalfLifeDays: Double = 30
    /// Matches `recommendations.ts`'s `VIEW_WEIGHT` / `SEARCH_WEIGHT` — a
    /// search carries half the weight of an actual view, before recency
    /// decay is applied on top.
    private static let viewWeight: Float = 1
    private static let searchWeight: Float = 0.5

    /// Ranks posts the user hasn't already viewed, most-recommended first.
    /// Falls back to "most important, most recent" (the same cold-start
    /// fallback the web app uses) when there's no view/search history yet,
    /// or nothing in it still has a parseable embedding.
    public static func recommend(
        posts: [Post],
        viewHistory: [ViewHistoryEntry],
        searchHistory: [SearchHistoryEntry] = [],
        limit: Int = 12
    ) -> [Post] {
        let viewedShortcodes = Set(viewHistory.map(\.shortcode))
        let candidates = posts.filter { !viewedShortcodes.contains($0.shortcode) }
        guard !candidates.isEmpty else { return [] }

        if let interestVector = buildInterestVector(posts: posts, viewHistory: viewHistory, searchHistory: searchHistory) {
            let scored = candidates.compactMap { post -> (post: Post, score: Float)? in
                guard let embedding = EmbeddingMath.parse(post.embedding) else { return nil }
                let normalized = EmbeddingMath.normalize(embedding)
                return (post, EmbeddingMath.cosineSimilarity(normalizedA: interestVector, normalizedB: normalized))
            }
            if !scored.isEmpty {
                return scored.sorted { $0.score > $1.score }.prefix(limit).map(\.post)
            }
        }

        return coldStartFallback(candidates: candidates, limit: limit)
    }

    private static func parseBackendDate(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let formatterNoFraction = ISO8601DateFormatter()
        formatterNoFraction.formatOptions = [.withInternetDateTime]
        let withOffset = raw.hasSuffix("Z") ? raw : raw + "Z"
        return formatter.date(from: withOffset) ?? formatterNoFraction.date(from: withOffset)
    }

    private static func recencyWeight(_ isoTimestamp: String, now: Date) -> Float {
        guard let date = parseBackendDate(isoTimestamp) else { return 0 }
        let ageDays = max(0, now.timeIntervalSince(date) / 86400)
        return Float(pow(0.5, ageDays / recencyHalfLifeDays))
    }

    private static func buildInterestVector(
        posts: [Post],
        viewHistory: [ViewHistoryEntry],
        searchHistory: [SearchHistoryEntry]
    ) -> [Float]? {
        guard !viewHistory.isEmpty || !searchHistory.isEmpty else { return nil }
        let postsByShortcode = Dictionary(posts.map { ($0.shortcode, $0) }, uniquingKeysWith: { first, _ in first })
        let now = Date()

        var weightedSum: [Float]?
        var totalWeight: Float = 0

        func accumulate(_ vector: [Float], weight: Float) {
            guard weight > 0 else { return }
            if weightedSum == nil {
                weightedSum = [Float](repeating: 0, count: vector.count)
            }
            guard weightedSum!.count == vector.count else { return }
            for index in vector.indices { weightedSum![index] += vector[index] * weight }
            totalWeight += weight
        }

        for view in viewHistory {
            guard let post = postsByShortcode[view.shortcode],
                  let embedding = EmbeddingMath.parse(post.embedding) else { continue }
            accumulate(EmbeddingMath.normalize(embedding), weight: viewWeight * recencyWeight(view.viewed_at, now: now))
        }

        for search in searchHistory {
            guard let queryEmbedding = search.query_embedding, !queryEmbedding.isEmpty else { continue }
            accumulate(EmbeddingMath.normalize(queryEmbedding), weight: searchWeight * recencyWeight(search.created_at, now: now))
        }

        guard var vector = weightedSum, totalWeight > 0 else { return nil }
        for index in vector.indices { vector[index] /= totalWeight }
        return EmbeddingMath.normalize(vector)
    }

    private static func coldStartFallback(candidates: [Post], limit: Int) -> [Post] {
        candidates
            .sorted { lhs, rhs in
                let lhsImportance = lhs.importance ?? 0
                let rhsImportance = rhs.importance ?? 0
                if lhsImportance != rhsImportance { return lhsImportance > rhsImportance }
                return (lhs.analyzed_at ?? "") > (rhs.analyzed_at ?? "")
            }
            .prefix(limit)
            .map { $0 }
    }
}
