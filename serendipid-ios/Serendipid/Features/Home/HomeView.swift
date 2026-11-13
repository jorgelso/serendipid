import SwiftUI
import SerendipidCore

struct HomeView: View {
    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @State private var viewModel: HomeViewModel?

    var body: some View {
        NavigationStack {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Your feed")
            .background(BrightPulse.background)
            .navigationDestination(for: String.self) { shortcode in
                PostDetailView(shortcode: shortcode)
            }
            .navigationDestination(for: DiscoverRoute.self) { _ in
                DiscoverView()
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    NavigationLink(value: DiscoverRoute()) {
                        Image(systemName: "chart.bar")
                    }
                }
            }
        }
        .task {
            if viewModel == nil {
                viewModel = HomeViewModel(dataStore: dataStore, configStore: configStore)
            }
            await viewModel?.loadIfNeeded()
        }
        .onAppear {
            Task { await viewModel?.retryIfNeeded() }
        }
    }

    @ViewBuilder
    private func content(viewModel: HomeViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            if viewModel.visiblePosts.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                feed(viewModel: viewModel)
            }
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            if viewModel.visiblePosts.isEmpty {
                EmptyStateView(systemImage: "tray", message: "Nothing here yet.")
            } else {
                feed(viewModel: viewModel)
            }
        }
    }

    private func feed(viewModel: HomeViewModel) -> some View {
        ScrollView {
            if !viewModel.recommendedPosts.isEmpty {
                recommendationsRail(viewModel: viewModel)
            }

            LazyVStack(spacing: 16) {
                ForEach(viewModel.visiblePosts) { post in
                    NavigationLink(value: post.shortcode) {
                        PostCardView(post: post, baseURL: viewModel.baseURL)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)

            if viewModel.hasMore {
                PillButton("Show more", style: .secondary) {
                    viewModel.loadMore()
                }
                .padding(.bottom, 24)
            }
        }
        .refreshable {
            await viewModel.refresh()
        }
    }

    private func recommendationsRail(viewModel: HomeViewModel) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recommended for you")
                .font(BrightPulseFont.display(size: 16, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
                .padding(.horizontal, 16)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(viewModel.recommendedPosts) { post in
                        NavigationLink(value: post.shortcode) {
                            PostCardView(post: post, baseURL: viewModel.baseURL)
                                .frame(width: 220)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
            }
        }
        .padding(.top, 16)
    }
}

struct EmptyStateView: View {
    let systemImage: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 32))
                .foregroundStyle(BrightPulse.inkMuted)
            Text(message)
                .font(BrightPulseFont.body(size: 15))
                .foregroundStyle(BrightPulse.inkMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
