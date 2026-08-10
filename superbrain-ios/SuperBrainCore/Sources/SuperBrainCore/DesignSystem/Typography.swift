import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The web app pairs Fredoka (display/headings) with Nunito (body) — both
/// open-source, freely embeddable Google Fonts. Bundling the actual TTFs into
/// the app target (`SuperBrain/Resources/Fonts/`, registered via `Info.plist`
/// `UIAppFonts`) gives exact visual parity; until those files are added,
/// `UIFont(name:size:)` returning nil makes every accessor below fall back to
/// SF Rounded automatically, so the app degrades gracefully rather than
/// silently using the wrong system font.
public enum BrightPulseFont {
    public static func display(size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        let name = displayFontName(for: weight)
        if fontExists(name) {
            return .custom(name, size: size)
        }
        return .system(size: size, weight: weight, design: .rounded)
    }

    public static func body(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let name = bodyFontName(for: weight)
        if fontExists(name) {
            return .custom(name, size: size)
        }
        return .system(size: size, weight: weight, design: .rounded)
    }

    private static func displayFontName(for weight: Font.Weight) -> String {
        switch weight {
        case .bold, .heavy, .black: return "Fredoka-SemiBold"
        case .semibold: return "Fredoka-SemiBold"
        case .medium: return "Fredoka-Medium"
        default: return "Fredoka-Regular"
        }
    }

    private static func bodyFontName(for weight: Font.Weight) -> String {
        switch weight {
        case .bold, .heavy, .black, .semibold: return "Nunito-Bold"
        default: return "Nunito-Regular"
        }
    }

    private static func fontExists(_ name: String) -> Bool {
        #if canImport(UIKit)
        return UIFont(name: name, size: 12) != nil
        #else
        return false
        #endif
    }
}
