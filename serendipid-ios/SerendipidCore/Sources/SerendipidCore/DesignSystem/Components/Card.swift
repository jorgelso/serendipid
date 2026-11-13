import SwiftUI

/// The base rounded-3xl (24pt) container with a soft shadow, used for post
/// cards, chat bubbles, and settings sections — mirrors the web app's card
/// styling (`rounded-3xl border border-line shadow-[...]`).
public struct Card<Content: View>: View {
    private let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        content
            .background(BrightPulse.surface)
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .strokeBorder(BrightPulse.line, lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.06), radius: 12, x: 0, y: 4)
    }
}
