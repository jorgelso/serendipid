import SwiftUI
import SuperBrainCore

/// Opened by tapping a theme in Insights — lists every post in that theme,
/// grouped by micro-cluster (the finer-grained sub-groups a theme is made
/// of), mirroring the web app's `ThemeAccordion` → `LazyPostList` structure.
struct ThemeDetailView: View {
    let theme: Theme

    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if !theme.subLabels.isEmpty {
                    Text(theme.subLabels.joined(separator: ", "))
                        .font(BrightPulseFont.body(size: 13))
                        .foregroundStyle(BrightPulse.inkMuted)
                        .padding(.horizontal, 16)
                }

                ForEach(theme.microClusters) { microCluster in
                    microClusterSection(microCluster)
                }
            }
            .padding(.vertical, 16)
        }
        .background(BrightPulse.background)
        .navigationTitle(theme.label)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func microClusterSection(_ microCluster: MicroCluster) -> some View {
        let posts = microCluster.postShortcodes.compactMap { dataStore.post(shortcode: $0) }

        return VStack(alignment: .leading, spacing: 10) {
            if theme.microClusters.count > 1 {
                HStack {
                    Text(microCluster.label)
                        .font(BrightPulseFont.display(size: 15, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                    Spacer()
                    Text("\(posts.count)")
                        .font(BrightPulseFont.body(size: 12))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                .padding(.horizontal, 16)
            }

            LazyVStack(spacing: 16) {
                ForEach(posts) { post in
                    NavigationLink(value: post.shortcode) {
                        PostCardView(post: post, baseURL: configStore.baseURL)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }
}
