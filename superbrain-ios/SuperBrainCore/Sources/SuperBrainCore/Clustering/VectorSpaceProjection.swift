import Foundation

/// Projects every post's 1536-dim embedding down to 3D for the Space tab,
/// and reuses `ThemeClustering.computeThemes`'s cosine-similarity clusters to
/// color the result instead of re-clustering from scratch — same split of
/// responsibilities as the web app's `computeVectorSpaceLayout`
/// (`superbrain-web/src/lib/vectorSpace.ts`), which delegates positioning to
/// UMAP. There's no Swift UMAP library, so positioning here uses **dual PCA
/// via the Gram-matrix trick** instead:
///
/// With N posts and D=1536 embedding dimensions, and N << D, the D×D
/// covariance matrix is far more expensive to work with than the N×N Gram
/// matrix `G = X·Xᵀ` (X = the N×D centered-embeddings matrix). The two are
/// related: if `v` is a unit eigenvector of the D×D covariance matrix with
/// eigenvalue `λ`, then `u = X·v` is an eigenvector of `G` with eigenvalue
/// `λ·(N-1)` — and critically, `u` **is** the per-post PCA score for that
/// component (up to the scaling that makes `u` unit-norm). So the top few
/// eigenvectors of `G`, scaled by `sqrt(eigenvalue)`, are directly usable as
/// per-post 3D coordinates — no need to ever materialize a D×D matrix.
/// Eigenvectors come from plain power iteration + deflation (repeatedly
/// apply `G`, normalize, subtract `λ·v·vᵀ` from `G`, repeat), which is the
/// standard way to get the top-k eigenpairs of a symmetric matrix without a
/// full eigendecomposition.
public enum VectorSpaceProjection {
    /// Below this, there aren't enough points for PCA's directions to mean
    /// anything — same threshold/rationale as the web app's
    /// `MIN_POINTS_FOR_UMAP`. Spread points on a small ring instead of
    /// crashing or projecting garbage/NaN.
    private static let minPointsForProjection = 4
    private static let targetRadius: Float = 20
    private static let componentCount = 3
    private static let powerIterationSteps = 60
    /// Arbitrary, fixed — keeps the layout's power-iteration starting vector
    /// (and therefore the final orientation of the point cloud) stable
    /// across recomputes, same rationale as the web app's `UMAP_SEED`.
    private static let seed: UInt64 = 0x5350_4143_4553_3231 // "SPACES21" in ASCII hex, arbitrary

    private struct ThemeAssignment {
        let colorSlot: VectorSpaceColorSlot
        let themeLabel: String
    }

    public static func compute(posts: [Post], themes: [Theme]) -> [VectorSpacePoint] {
        let postsByShortcode = Dictionary(uniqueKeysWithValues: posts.map { ($0.shortcode, $0) })
        let themeAssignments = buildThemeAssignments(themes)

        var shortcodes: [String] = []
        var vectors: [[Float]] = []
        for post in posts {
            guard let vector = EmbeddingMath.parse(post.embedding), !vector.isEmpty else { continue }
            shortcodes.append(post.shortcode)
            vectors.append(vector)
        }
        guard !vectors.isEmpty else { return [] }

        let rawPositions = vectors.count < minPointsForProjection
            ? fallbackLayout(count: vectors.count)
            : dualPCA(vectors: vectors)
        let positions = normalizeLayout(rawPositions)

        return shortcodes.indices.map { index in
            let shortcode = shortcodes[index]
            let post = postsByShortcode[shortcode]
            let assignment = themeAssignments[shortcode]
            return VectorSpacePoint(
                shortcode: shortcode,
                position: positions[index],
                colorSlot: assignment?.colorSlot ?? .unclustered,
                themeLabel: assignment?.themeLabel ?? "Unclustered",
                title: post?.title,
                thumbnail: post?.thumbnail,
                category: post?.category ?? []
            )
        }
    }

    /// The first 8 themes (already sorted largest-first by
    /// `ThemeClustering.computeThemes`) get one of the 8 validated
    /// categorical hues; everything past that folds into `.other` rather
    /// than cycling colors.
    private static func buildThemeAssignments(_ themes: [Theme]) -> [String: ThemeAssignment] {
        var map: [String: ThemeAssignment] = [:]
        for (themeIndex, theme) in themes.enumerated() {
            let slot: VectorSpaceColorSlot = themeIndex < 8 ? .theme(themeIndex) : .other
            let assignment = ThemeAssignment(colorSlot: slot, themeLabel: theme.label)
            for microCluster in theme.microClusters {
                for shortcode in microCluster.postShortcodes {
                    map[shortcode] = assignment
                }
            }
        }
        return map
    }

    // MARK: - Dual PCA via the Gram-matrix trick

    private static func dualPCA(vectors: [[Float]]) -> [SIMD3<Float>] {
        let n = vectors.count
        let dimension = vectors[0].count

        // Center across samples: subtract the mean embedding (per-dimension)
        // from every post's vector — required for PCA's directions to mean
        // "variance", not just "distance from the origin".
        var mean = [Float](repeating: 0, count: dimension)
        for vector in vectors {
            for d in 0..<dimension { mean[d] += vector[d] }
        }
        for d in 0..<dimension { mean[d] /= Float(n) }
        let centered = vectors.map { vector -> [Float] in
            var result = [Float](repeating: 0, count: dimension)
            for d in 0..<dimension { result[d] = vector[d] - mean[d] }
            return result
        }

        // Gram matrix G = X_centered · X_centeredᵀ (N×N, symmetric).
        var gram = [[Float]](repeating: [Float](repeating: 0, count: n), count: n)
        for i in 0..<n {
            gram[i][i] = EmbeddingMath.dot(centered[i], centered[i])
            for j in (i + 1)..<n {
                let value = EmbeddingMath.dot(centered[i], centered[j])
                gram[i][j] = value
                gram[j][i] = value
            }
        }

        var rng = SeededGenerator(seed: seed)
        // Each entry is a length-N vector: the per-post scalar coordinate
        // for that principal component.
        var components: [[Float]] = []

        for _ in 0..<componentCount {
            var vector = (0..<n).map { _ in Float.random(in: -1...1, using: &rng) }
            normalizeInPlace(&vector)

            for _ in 0..<powerIterationSteps {
                var next = [Float](repeating: 0, count: n)
                for i in 0..<n {
                    var sum: Float = 0
                    let row = gram[i]
                    for j in 0..<n { sum += row[j] * vector[j] }
                    next[i] = sum
                }
                let magnitude = sqrt(next.reduce(Float(0)) { $0 + $1 * $1 })
                guard magnitude > 1e-12 else { break }
                for i in 0..<n { next[i] /= magnitude }
                vector = next
            }

            // Rayleigh quotient vᵀGv gives the eigenvalue (vector is
            // unit-norm at this point).
            var gv = [Float](repeating: 0, count: n)
            for i in 0..<n {
                var sum: Float = 0
                let row = gram[i]
                for j in 0..<n { sum += row[j] * vector[j] }
                gv[i] = sum
            }
            let eigenvalue = max(EmbeddingMath.dot(vector, gv), 0)
            let scale = sqrt(eigenvalue)
            components.append(vector.map { $0 * scale })

            guard eigenvalue > 1e-9 else { continue }
            // Deflate: remove this component's contribution so the next
            // power-iteration pass converges to the next-largest eigenpair.
            for i in 0..<n {
                for j in 0..<n {
                    gram[i][j] -= eigenvalue * vector[i] * vector[j]
                }
            }
        }

        while components.count < componentCount {
            components.append([Float](repeating: 0, count: n))
        }

        return (0..<n).map { i in
            SIMD3<Float>(components[0][i], components[1][i], components[2][i])
        }
    }

    private static func normalizeInPlace(_ vector: inout [Float]) {
        let magnitude = sqrt(vector.reduce(Float(0)) { $0 + $1 * $1 })
        guard magnitude > 0 else { return }
        for i in vector.indices { vector[i] /= magnitude }
    }

    // MARK: - Fallback layout for too-few points

    /// Below `minPointsForProjection`, spread points evenly on a small ring
    /// rather than running PCA on a near-empty Gram matrix.
    private static func fallbackLayout(count: Int) -> [SIMD3<Float>] {
        guard count > 0 else { return [] }
        if count == 1 { return [SIMD3<Float>(0, 0, 0)] }
        var positions: [SIMD3<Float>] = []
        positions.reserveCapacity(count)
        for i in 0..<count {
            let angle = Float(2 * Double.pi * Double(i) / Double(count))
            positions.append(SIMD3<Float>(cos(angle) * targetRadius * 0.3, 0, sin(angle) * targetRadius * 0.3))
        }
        return positions
    }

    /// Recenters on the centroid and uniformly rescales (same factor on
    /// every axis, so relative distances aren't distorted) to a consistent
    /// on-screen radius regardless of dataset size or PCA's raw output
    /// scale — a straightforward normalize-by-max-magnitude step.
    private static func normalizeLayout(_ raw: [SIMD3<Float>]) -> [SIMD3<Float>] {
        guard !raw.isEmpty else { return [] }

        var sum = SIMD3<Float>(0, 0, 0)
        for p in raw { sum = SIMD3<Float>(sum.x + p.x, sum.y + p.y, sum.z + p.z) }
        let centroid = SIMD3<Float>(sum.x / Float(raw.count), sum.y / Float(raw.count), sum.z / Float(raw.count))

        let centered = raw.map { SIMD3<Float>($0.x - centroid.x, $0.y - centroid.y, $0.z - centroid.z) }

        var maxDistance: Float = 0
        for p in centered {
            let distance = sqrt(p.x * p.x + p.y * p.y + p.z * p.z)
            maxDistance = max(maxDistance, distance)
        }
        guard maxDistance > 0 else { return centered }

        let scale = targetRadius / maxDistance
        return centered.map { SIMD3<Float>($0.x * scale, $0.y * scale, $0.z * scale) }
    }
}

/// Deterministic xorshift64 RNG — fixed-seed so the projection's
/// power-iteration starting vectors (and therefore the final layout
/// orientation) are stable across recomputes instead of jumping every time
/// the cache invalidates. Not cryptographic, doesn't need to be.
private struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        self.state = seed == 0 ? 0x9E37_79B9_7F4A_7C15 : seed
    }

    mutating func next() -> UInt64 {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }
}
