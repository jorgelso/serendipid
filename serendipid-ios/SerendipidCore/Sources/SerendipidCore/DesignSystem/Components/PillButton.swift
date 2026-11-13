import SwiftUI

public enum PillButtonStyle {
    /// Solid ink/coral fill, white/light text — primary CTA.
    case primary
    /// Soft-tint fill, ink-colored text — secondary action.
    case secondary
}

/// Fully-rounded pill button, the web app's dominant CTA shape
/// (`rounded-full`, `font-display font-semibold`).
public struct PillButton: View {
    private let title: String
    private let style: PillButtonStyle
    private let isLoading: Bool
    private let action: () -> Void

    public init(_ title: String, style: PillButtonStyle = .primary, isLoading: Bool = false, action: @escaping () -> Void) {
        self.title = title
        self.style = style
        self.isLoading = isLoading
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if isLoading {
                    ProgressView()
                        .tint(foreground)
                        .scaleEffect(0.8)
                }
                Text(title)
                    .font(BrightPulseFont.display(size: 15, weight: .semibold))
            }
            .foregroundStyle(foreground)
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Capsule().fill(background))
        }
        .disabled(isLoading)
        .opacity(isLoading ? 0.7 : 1)
    }

    private var background: Color {
        switch style {
        case .primary: return BrightPulse.coral
        case .secondary: return BrightPulse.coralSoft
        }
    }

    private var foreground: Color {
        switch style {
        case .primary: return .white
        case .secondary: return BrightPulse.coralInk
        }
    }
}
