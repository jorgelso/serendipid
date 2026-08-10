import SwiftUI

struct RootTabView: View {
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
            InsightsView()
                .tabItem { Label("Insights", systemImage: "chart.bar") }
            SpacePlaceholderView()
                .tabItem { Label("Space", systemImage: "circle.hexagongrid") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
    }
}

#Preview {
    RootTabView()
}
