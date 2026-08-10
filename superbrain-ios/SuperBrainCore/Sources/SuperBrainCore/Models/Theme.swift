import Foundation

/// Purely client-computed (no backend endpoint) — mirrors
/// `superbrain-web/src/lib/clustering.ts`'s output shapes.
public struct MicroCluster: Identifiable, Hashable, Sendable {
    public let id: String
    public let label: String
    public let subLabels: [String]
    public let postShortcodes: [String]
}

public struct Theme: Identifiable, Hashable, Sendable {
    public let id: String
    public let label: String
    public let subLabels: [String]
    public let postCount: Int
    public let microClusters: [MicroCluster]
}
