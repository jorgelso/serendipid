import SwiftUI

/// Generalizes `serendipid-web/src/components/Chips.tsx`'s pill shape — used
/// for category/tag/language badges. Small, bold, uppercase-tracking text on
/// a soft-tint rounded-full background, per the web app's badge styling.
public struct PillBadge: View {
    private let text: String
    private let background: Color
    private let foreground: Color
    private let uppercase: Bool

    public init(_ text: String, background: Color, foreground: Color, uppercase: Bool = true) {
        self.text = text
        self.background = background
        self.foreground = foreground
        self.uppercase = uppercase
    }

    public var body: some View {
        Text(uppercase ? text.uppercased() : text)
            .font(BrightPulseFont.body(size: 11, weight: .bold))
            .tracking(0.4)
            .foregroundStyle(foreground)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Capsule().fill(background))
    }
}

/// A category/tag pill whose color is deterministically hashed from its
/// label text via `BrightPulse.colorFor`.
public struct LabelPill: View {
    private let label: String
    private let uppercase: Bool

    public init(_ label: String, uppercase: Bool = true) {
        self.label = label
        self.uppercase = uppercase
    }

    public var body: some View {
        let colors = BrightPulse.colorFor(label)
        PillBadge(label, background: colors.soft, foreground: colors.ink, uppercase: uppercase)
    }
}
