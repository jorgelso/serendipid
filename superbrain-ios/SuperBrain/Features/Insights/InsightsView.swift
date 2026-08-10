import SwiftUI
import SuperBrainCore

struct InsightsView: View {
    @Environment(AppDataStore.self) private var dataStore
    @State private var viewModel: InsightsViewModel?

    var body: some View {
        NavigationStack {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Insights")
            .background(BrightPulse.background)
            .navigationDestination(for: Theme.self) { theme in
                ThemeDetailView(theme: theme)
            }
            .navigationDestination(for: String.self) { shortcode in
                PostDetailView(shortcode: shortcode)
            }
        }
        .task {
            if viewModel == nil {
                viewModel = InsightsViewModel(dataStore: dataStore)
            }
            await viewModel?.loadIfNeeded()
        }
        .onAppear {
            Task { await viewModel?.retryIfNeeded() }
        }
    }

    @ViewBuilder
    private func content(viewModel: InsightsViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if viewModel.needsReviewCount > 0 {
                        needsReviewBanner(viewModel: viewModel)
                    }

                    section(title: "\(viewModel.totalPosts) saved posts", subtitle: "by category") {
                        StatBarsView(entries: viewModel.categoryCounts)
                    }
                    section(title: "By language") {
                        StatBarsView(entries: viewModel.languageCounts)
                    }
                    section(title: "Most common tags") {
                        StatBarsView(entries: viewModel.tagCounts)
                    }

                    if FeatureFlags.clusteringEnabled {
                        section(title: "Themes it noticed", subtitle: "Grouped automatically by comparing what each post is actually about.") {
                            if viewModel.themes.isEmpty {
                                Text("No themes yet — as more of your saved reels get analyzed, related ones will start grouping here on their own.")
                                    .font(BrightPulseFont.body(size: 13))
                                    .foregroundStyle(BrightPulse.inkMuted)
                            } else {
                                ForEach(viewModel.themes) { theme in
                                    NavigationLink(value: theme) {
                                        ThemeRow(theme: theme)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
                .padding(16)
            }
            .refreshable { await viewModel.refresh() }
        }
    }

    private func needsReviewBanner(viewModel: InsightsViewModel) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(viewModel.needsReviewCount) of \(viewModel.totalPosts) posts need review")
                .font(BrightPulseFont.body(size: 14, weight: .semibold))
                .foregroundStyle(BrightPulse.yellowInk)
            Text("Categorized under an older version of the analysis pipeline. Open a post in Browse or Search and use \"Re-run analysis\" or \"Keep as is\" on it.")
                .font(BrightPulseFont.body(size: 12))
                .foregroundStyle(BrightPulse.inkMuted)
        }
        .padding(14)
        .background(BrightPulse.yellowSoft)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func section<Content: View>(title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(BrightPulseFont.display(size: 17, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
            if let subtitle {
                Text(subtitle)
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
            content()
        }
    }
}

private struct ThemeRow: View {
    let theme: Theme

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(theme.label)
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
                Spacer()
                Text("\(theme.postCount) saved")
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(BrightPulse.inkMuted)
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
            if !theme.subLabels.isEmpty {
                Text(theme.subLabels.joined(separator: ", "))
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
        .padding(12)
        .background(BrightPulse.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
