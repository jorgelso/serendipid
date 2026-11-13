import SwiftUI
import SerendipidCore

/// Exactly 5 tabs — Apple's tab bar auto-collapses a 6th+ item into a "More"
/// tab, which changes navigation behavior in a way that's easy to miss during
/// development (everything still "works" on a device with a wide-enough tab
/// bar). Insights and Space moved off the tab bar into `DiscoverView`,
/// reachable from Home's toolbar, to stay under that limit.
struct RootTabView: View {
    @Environment(\.apiClient) private var apiClient
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house.fill") }
            BrowseView()
                .tabItem { Label("Browse", systemImage: "square.grid.2x2") }
            SearchView()
                .tabItem { Label("Search", systemImage: "magnifyingglass") }
            ChatThreadListView()
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .task {
            await syncPendingShares()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await syncPendingShares() }
            }
        }
    }

    /// Drains any shares the Share Extension couldn't reach the backend with
    /// (`PendingShareStore`) — runs at launch and every time the app comes
    /// back to the foreground, since "backend was unreachable" is exactly the
    /// condition that tends to resolve itself between share and next open
    /// (phone back on the home network, laptop server awake again).
    private func syncPendingShares() async {
        let store = PendingShareStore()
        guard store.count > 0 else { return }
        let syncer = PendingShareSyncer(apiClient: apiClient, store: store)
        await syncer.flush()
    }
}

#Preview {
    RootTabView()
}
