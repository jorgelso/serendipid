import Foundation

/// Pure math over the 1536-dim OpenAI embeddings `/export` includes per post
/// (JSON-text encoded). No Accelerate/vDSP dependency — cosine similarity
/// over a personal library's post count is comfortably fast as plain Swift.
public enum EmbeddingMath {
    public static func parse(_ jsonText: String?) -> [Float]? {
        guard let jsonText, !jsonText.isEmpty, let data = jsonText.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([Float].self, from: data)
    }

    public static func normalize(_ vector: [Float]) -> [Float] {
        let magnitude = sqrt(vector.reduce(Float(0)) { $0 + $1 * $1 })
        guard magnitude > 0 else { return vector }
        return vector.map { $0 / magnitude }
    }

    public static func dot(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count else { return 0 }
        var sum: Float = 0
        for index in a.indices { sum += a[index] * b[index] }
        return sum
    }

    /// Assumes both vectors are already normalized (callers that compare many
    /// pairs against the same vectors should normalize once up front).
    public static func cosineSimilarity(normalizedA a: [Float], normalizedB b: [Float]) -> Float {
        dot(a, b)
    }

    public static func averageVector(_ vectors: [[Float]]) -> [Float] {
        guard let first = vectors.first else { return [] }
        var sum = [Float](repeating: 0, count: first.count)
        for vector in vectors {
            for index in vector.indices { sum[index] += vector[index] }
        }
        return sum.map { $0 / Float(vectors.count) }
    }
}
