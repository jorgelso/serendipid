import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// SwiftUI has no `color-mix()` equivalent — this linearly interpolates two
/// colors' RGB components, used by `VersionBehindBadge`/`ImportanceBadge` to
/// port the web app's `color-mix(red, green)` gradient badges.
extension Color {
    public static func lerp(_ from: Color, _ to: Color, t: Double) -> Color {
        let t = min(max(t, 0), 1)
        #if canImport(UIKit)
        let fromComponents = UIColor(from).rgbaComponents
        let toComponents = UIColor(to).rgbaComponents
        return Color(
            red: fromComponents.r + (toComponents.r - fromComponents.r) * t,
            green: fromComponents.g + (toComponents.g - fromComponents.g) * t,
            blue: fromComponents.b + (toComponents.b - fromComponents.b) * t,
            opacity: fromComponents.a + (toComponents.a - fromComponents.a) * t
        )
        #else
        return t < 0.5 ? from : to
        #endif
    }
}

#if canImport(UIKit)
private extension UIColor {
    var rgbaComponents: (r: Double, g: Double, b: Double, a: Double) {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Double(r), Double(g), Double(b), Double(a))
    }
}
#endif
