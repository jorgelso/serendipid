import SwiftUI

/// "N version(s) behind" pill, only shown when `post.needs_review` — color
/// lerps from danger (red, far behind) to mint (green, barely behind), same
/// idea as the web app's `color-mix(red, green)` gradient.
public struct VersionBehindBadge: View {
    private let versionsBehind: Int
    private let maxExpectedGap: Int

    public init(versionsBehind: Int, maxExpectedGap: Int = 5) {
        self.versionsBehind = max(versionsBehind, 0)
        self.maxExpectedGap = max(maxExpectedGap, 1)
    }

    public var body: some View {
        let t = Double(min(versionsBehind, maxExpectedGap)) / Double(maxExpectedGap)
        let background = Color.lerp(BrightPulse.mintSoft, BrightPulse.dangerSoft, t: t)
        let foreground = Color.lerp(BrightPulse.mintInk, BrightPulse.danger, t: t)
        PillBadge(
            "\(versionsBehind) version\(versionsBehind == 1 ? "" : "s") behind",
            background: background,
            foreground: foreground
        )
    }
}

/// 1-5 importance score pill — nil/unscored posts should not render this at
/// all (never treat nil as 0).
public struct ImportanceBadge: View {
    private let importance: Int

    public init?(importance: Int?) {
        guard let importance, (1...5).contains(importance) else { return nil }
        self.importance = importance
    }

    public var body: some View {
        let t = Double(importance - 1) / 4.0
        let background = Color.lerp(BrightPulse.surface2, BrightPulse.yellowSoft, t: t)
        let foreground = Color.lerp(BrightPulse.inkMuted, BrightPulse.yellowInk, t: t)
        PillBadge(String(repeating: "★", count: importance), background: background, foreground: foreground, uppercase: false)
    }
}
