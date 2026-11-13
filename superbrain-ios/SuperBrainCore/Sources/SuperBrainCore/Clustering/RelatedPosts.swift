import Foundation

/// A post scored against another post's embedding, for the Post Detail
/// "Related" rail.
public struct RelatedPost: Identifiable, Sendable {
    public var id: String { post.shortcode }
    public let post: Post
    public let similarity: Float
}

/// O(n) cosine-similarity nearest-neighbor ranking — ports
/// `superbrain-web/src/lib/clustering.ts`'s `findRelatedPosts`. Cheap enough
/// to run on every Post Detail open, unlike the O(n²) theme clustering in
/// `ThemeClustering`.
public enum RelatedPosts {
    public static func find(for target: Post, in posts: [Post], limit: Int = 8) -> [RelatedPost] {
        guard let targetVector = EmbeddingMath.parse(target.embedding) else { return [] }
        let normalizedTarget = EmbeddingMath.normalize(targetVector)

        var scored: [RelatedPost] = []
        // Never suggest a sensitive-folder post (backend/core/sensitive.py).
        for candidate in posts where candidate.shortcode != target.shortcode && candidate.is_sensitive != 1 {
            guard let candidateVector = EmbeddingMath.parse(candidate.embedding) else { continue }
            let similarity = EmbeddingMath.cosineSimilarity(
                normalizedA: normalizedTarget,
                normalizedB: EmbeddingMath.normalize(candidateVector)
            )
            scored.append(RelatedPost(post: candidate, similarity: similarity))
        }

        return Array(scored.sorted { $0.similarity > $1.similarity }.prefix(limit))
    }
}
