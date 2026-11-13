import Foundation

/// Two-pass hierarchical cosine-similarity clustering over post embeddings —
/// ports `serendipid-web/src/lib/clustering.ts`'s `computeThemes`. Pure,
/// dependency-free math (union-find connected components), no LLM calls, no
/// UMAP. Gated by `FeatureFlags.clusteringEnabled` — see that file.
public enum ThemeClustering {
    private static let fineThreshold: Float = 0.72
    private static let coarseThreshold: Float = 0.7
    private static let minThemeSize = 3

    private static let genericTags: Set<String> = [
        "instagramreel", "reels", "reel", "viral", "fyp", "explore", "explorepage",
        "trending", "instagram", "instagood", "video", "follow", "like", "share",
    ]

    public static func computeThemes(posts: [Post]) -> (themes: [Theme], unclusteredShortcodes: [String]) {
        let postsByShortcode = Dictionary(uniqueKeysWithValues: posts.map { ($0.shortcode, $0) })

        let embedded: [(shortcode: String, vector: [Float])] = posts.compactMap { post in
            guard let vector = EmbeddingMath.parse(post.embedding), !vector.isEmpty else { return nil }
            return (post.shortcode, vector)
        }

        guard embedded.count >= 2 else {
            return ([], posts.map(\.shortcode))
        }

        let normalizedEmbedded = embedded.map { EmbeddingMath.normalize($0.vector) }
        let microGroups = connectedComponents(normalizedVectors: normalizedEmbedded, threshold: fineThreshold)

        var microClusters: [MicroCluster] = []
        var microCentroids: [[Float]] = []
        for group in microGroups {
            let shortcodes = group.map { embedded[$0].shortcode }
            let centroid = EmbeddingMath.averageVector(group.map { normalizedEmbedded[$0] })
            let (labelText, subLabels) = labelFromPosts(shortcodes: shortcodes, posts: postsByShortcode)
            microClusters.append(
                MicroCluster(id: "micro-\(microClusters.count)", label: labelText, subLabels: subLabels, postShortcodes: shortcodes)
            )
            microCentroids.append(EmbeddingMath.normalize(centroid))
        }

        guard microClusters.count >= 2 else {
            let clustered = Set(microClusters.flatMap(\.postShortcodes))
            let unclustered = Set(posts.map(\.shortcode)).subtracting(clustered)
            return ([], Array(unclustered))
        }

        let themeGroups = connectedComponents(normalizedVectors: microCentroids, threshold: coarseThreshold)

        var themes: [Theme] = []
        var clusteredShortcodes = Set<String>()
        for group in themeGroups {
            let memberClusters = group.map { microClusters[$0] }
            let allShortcodes = memberClusters.flatMap(\.postShortcodes)
            guard allShortcodes.count >= minThemeSize else { continue }
            let (labelText, subLabels) = labelFromPosts(shortcodes: allShortcodes, posts: postsByShortcode)
            themes.append(
                Theme(id: "theme-\(themes.count)", label: labelText, subLabels: subLabels, postCount: allShortcodes.count, microClusters: memberClusters)
            )
            clusteredShortcodes.formUnion(allShortcodes)
        }

        themes.sort { $0.postCount > $1.postCount }
        let unclustered = Set(posts.map(\.shortcode)).subtracting(clusteredShortcodes)
        return (themes, Array(unclustered))
    }

    /// Union-find connected components: two vectors in the same component if
    /// there's a chain of pairwise similarities each >= threshold.
    private static func connectedComponents(normalizedVectors: [[Float]], threshold: Float) -> [[Int]] {
        var parent = Array(normalizedVectors.indices)
        func find(_ x: Int) -> Int {
            var x = x
            while parent[x] != x {
                parent[x] = parent[parent[x]]
                x = parent[x]
            }
            return x
        }
        func union(_ a: Int, _ b: Int) {
            let rootA = find(a), rootB = find(b)
            if rootA != rootB { parent[rootB] = rootA }
        }

        for i in normalizedVectors.indices {
            for j in (i + 1)..<normalizedVectors.count {
                if EmbeddingMath.dot(normalizedVectors[i], normalizedVectors[j]) >= threshold {
                    union(i, j)
                }
            }
        }

        var groups: [Int: [Int]] = [:]
        for i in normalizedVectors.indices {
            groups[find(i), default: []].append(i)
        }
        return Array(groups.values)
    }

    private static func labelFromPosts(shortcodes: [String], posts: [String: Post]) -> (label: String, subLabels: [String]) {
        var tagCounts: [String: Int] = [:]
        var categoryCounts: [String: Int] = [:]
        for shortcode in shortcodes {
            guard let post = posts[shortcode] else { continue }
            for tag in post.tags where !genericTags.contains(tag.lowercased()) {
                tagCounts[tag, default: 0] += 1
            }
            for category in post.category {
                categoryCounts[category, default: 0] += 1
            }
        }

        let subLabels = Array(categoryCounts.sorted { $0.value > $1.value }.prefix(3).map(\.key))

        if let topTag = tagCounts.max(by: { $0.value < $1.value }) {
            return (topTag.key, subLabels)
        }
        if let topCategory = categoryCounts.max(by: { $0.value < $1.value }) {
            return (topCategory.key, [])
        }
        return ("Uncategorized", [])
    }
}
