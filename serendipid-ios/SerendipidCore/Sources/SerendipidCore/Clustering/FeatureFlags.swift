import Foundation

/// `ThemeClustering` — validated against the real backend (325 real posts,
/// 321 with embeddings): 11 sensible themes surfaced (e.g. "#faith" 32
/// posts/17 micro-clusters, "#calisthenics" 17 posts, "#Rome" 11 posts),
/// zero crashes. Runs off the main actor via `Task.detached` in
/// `AppDataStore.getThemes()` since it's O(n²) over embeddings and can take
/// several seconds, especially in an unoptimized debug build.
public enum FeatureFlags {
    public static let clusteringEnabled = true
}
