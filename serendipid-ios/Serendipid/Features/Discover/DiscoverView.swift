import SwiftUI

/// Hashable marker for pushing `DiscoverView` via `NavigationLink(value:)`
/// from Home's toolbar — see `RootTabView`'s doc comment for why Insights and
/// Space live here instead of as their own tabs.
struct DiscoverRoute: Hashable {}

/// Insights and Space, switched by a segmented control instead of separate
/// tabs. Deliberately *not* its own `NavigationStack` — it's pushed onto
/// Home's existing stack (`HomeView`'s toolbar → `DiscoverRoute`), and
/// InsightsView/SpaceView register their `navigationDestination`s directly
/// onto that same ambient stack. Nesting a second `NavigationStack` here
/// would instead produce two stacked navigation bars (a known SwiftUI
/// gotcha), so this view contributes only content, not stack structure.
struct DiscoverView: View {
    private enum Mode: String, CaseIterable, Identifiable {
        case insights = "Insights"
        case space = "Space"
        var id: String { rawValue }
    }

    @State private var mode: Mode = .insights

    var body: some View {
        VStack(spacing: 0) {
            Picker("View", selection: $mode) {
                ForEach(Mode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 4)

            switch mode {
            case .insights: InsightsView()
            case .space: SpaceView()
            }
        }
    }
}
