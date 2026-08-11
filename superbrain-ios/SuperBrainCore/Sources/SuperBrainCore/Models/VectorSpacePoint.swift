import Foundation

/// Which categorical color a point renders as — mirrors the web app's
/// `VectorSpaceColorSlot` (`superbrain-web/src/types/domain.ts`), but as a
/// Swift enum instead of a `theme-${number}` string union. The first 8
/// themes (already sorted largest-first by `ThemeClustering.computeThemes`)
/// each get one of `BrightPulse.vizSeriesHexLight/Dark`'s 8 slots; anything
/// past that (or not in any theme at all) folds into `.other`/`.unclustered`
/// rather than cycling colors, per the dataviz skill's categorical-series cap.
public enum VectorSpaceColorSlot: Hashable, Sendable {
    case theme(Int)
    case other
    case unclustered
}

/// One saved post plotted in the 3D "vector space" — `VectorSpaceProjection`
/// produces these from a dual-PCA projection of the post's embedding, colored
/// by the theme assignment `ThemeClustering.computeThemes` already computed
/// (no re-clustering here). Mirrors the web app's `VectorSpacePoint`
/// (`superbrain-web/src/types/domain.ts`), minus the `videoUrl` field the web
/// scene needs for hover-preview video playback but the native SceneKit view
/// doesn't.
public struct VectorSpacePoint: Identifiable, Hashable, Sendable {
    public var id: String { shortcode }

    public let shortcode: String
    public let position: SIMD3<Float>
    public let colorSlot: VectorSpaceColorSlot
    public let themeLabel: String
    public let title: String?
    public let thumbnail: String?
    public let category: [String]

    public init(
        shortcode: String, position: SIMD3<Float>, colorSlot: VectorSpaceColorSlot,
        themeLabel: String, title: String?, thumbnail: String?, category: [String]
    ) {
        self.shortcode = shortcode
        self.position = position
        self.colorSlot = colorSlot
        self.themeLabel = themeLabel
        self.title = title
        self.thumbnail = thumbnail
        self.category = category
    }
}
