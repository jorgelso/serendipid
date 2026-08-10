import SwiftUI

/// The web app's "Bright Pulse" design system — warm, playful, visual-first.
/// Every accent hue is a base/soft/ink triplet (base = solid fills, soft =
/// pale pill/badge background, ink = readable-on-soft text color), sourced
/// directly from `superbrain-web/src/app/globals.css`'s light/dark blocks as
/// Any/Dark Color Set assets in `Resources/Colors.xcassets` — see that
/// catalog for the actual hex values.
public enum BrightPulse {
    public static let background = Color("bgColor", bundle: .module)
    public static let surface = Color("surfaceColor", bundle: .module)
    public static let surface2 = Color("surface2Color", bundle: .module)
    public static let ink = Color("inkColor", bundle: .module)
    public static let inkMuted = Color("inkMutedColor", bundle: .module)
    public static let line = Color("lineColor", bundle: .module)

    public static let coral = Color("coral", bundle: .module)
    public static let coralSoft = Color("coralSoft", bundle: .module)
    public static let coralInk = Color("coralInk", bundle: .module)

    public static let yellow = Color("yellow", bundle: .module)
    public static let yellowSoft = Color("yellowSoft", bundle: .module)
    public static let yellowInk = Color("yellowInk", bundle: .module)

    public static let teal = Color("teal", bundle: .module)
    public static let tealSoft = Color("tealSoft", bundle: .module)
    public static let tealInk = Color("tealInk", bundle: .module)

    public static let lavender = Color("lavender", bundle: .module)
    public static let lavenderSoft = Color("lavenderSoft", bundle: .module)
    public static let lavenderInk = Color("lavenderInk", bundle: .module)

    public static let mint = Color("mint", bundle: .module)
    public static let mintSoft = Color("mintSoft", bundle: .module)
    public static let mintInk = Color("mintInk", bundle: .module)

    public static let rose = Color("rose", bundle: .module)
    public static let roseSoft = Color("roseSoft", bundle: .module)
    public static let roseInk = Color("roseInk", bundle: .module)

    public static let sky = Color("sky", bundle: .module)
    public static let skySoft = Color("skySoft", bundle: .module)
    public static let skyInk = Color("skyInk", bundle: .module)

    public static let danger = Color("danger", bundle: .module)
    public static let dangerSoft = Color("dangerSoft", bundle: .module)

    /// The 7-entry soft/ink rotation `colorFor(label)` hashes tags/categories
    /// into, matching `superbrain-web/src/components/Chips.tsx` so the same
    /// label renders the same color on both clients.
    public static let tagPalette: [(soft: Color, ink: Color)] = [
        (coralSoft, coralInk),
        (tealSoft, tealInk),
        (yellowSoft, yellowInk),
        (lavenderSoft, lavenderInk),
        (mintSoft, mintInk),
        (roseSoft, roseInk),
        (skySoft, skyInk),
    ]

    /// Deterministic hash → stable color per label, so "Cooking" always gets
    /// the same pill color everywhere in the app (and matches the web app's
    /// `colorFor()` rotation length, though not necessarily the exact same
    /// hash function — both just need to be *stable*, not identical).
    public static func colorFor(_ label: String) -> (soft: Color, ink: Color) {
        var hash = 0
        for scalar in label.unicodeScalars {
            hash = (hash &* 31) &+ Int(scalar.value)
        }
        let index = abs(hash) % tagPalette.count
        return tagPalette[index]
    }

    /// The 8-hue categorical palette for Insights charts / the (deferred)
    /// Space view — deliberately separate from the accent triplets above,
    /// since the brand hues fail CVD-separation validation as a scatter/bar
    /// categorical set. Raw hex, not Color Set assets, since Space's
    /// RealityKit materials need real RGB, not a resolved SwiftUI `Color`
    /// (mirrors the web app's `useVizPalette.ts` rationale).
    public static let vizSeriesHexLight: [String] = [
        "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
        "#e87ba4", "#008300", "#4a3aa7", "#e34948",
    ]
    public static let vizSeriesHexDark: [String] = [
        "#5b9ee8", "#f08a5e", "#3fca94", "#f0b431",
        "#f094b6", "#2ea82e", "#7364c9", "#f07270",
    ]
}
