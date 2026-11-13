import SwiftUI
import SerendipidCore

struct BrowseView: View {
    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @State private var viewModel: BrowseViewModel?

    var body: some View {
        NavigationStack {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Browse")
            .background(BrightPulse.background)
            .navigationDestination(for: String.self) { shortcode in
                PostDetailView(shortcode: shortcode)
            }
        }
        .task {
            if viewModel == nil {
                viewModel = BrowseViewModel(dataStore: dataStore, configStore: configStore)
            }
            await viewModel?.loadIfNeeded()
        }
        .onAppear {
            Task { await viewModel?.retryIfNeeded() }
        }
    }

    @ViewBuilder
    private func content(viewModel: BrowseViewModel) -> some View {
        VStack(spacing: 0) {
            BrowseFiltersView(
                categories: viewModel.categoryOptions,
                languages: viewModel.languageOptions,
                collections: viewModel.collections,
                selectedCategory: Binding(
                    get: { viewModel.selectedCategory },
                    set: { viewModel.selectedCategory = $0; viewModel.onFilterChanged() }
                ),
                selectedLanguage: Binding(
                    get: { viewModel.selectedLanguage },
                    set: { viewModel.selectedLanguage = $0; viewModel.onFilterChanged() }
                ),
                selectedCollectionID: Binding(
                    get: { viewModel.selectedCollectionID },
                    set: { viewModel.selectedCollectionID = $0; viewModel.onFilterChanged() }
                ),
                selectedEloquenceFilter: Binding(
                    get: { viewModel.selectedEloquenceFilter },
                    set: { viewModel.selectedEloquenceFilter = $0; viewModel.onFilterChanged() }
                ),
                sortOrder: Binding(
                    get: { viewModel.sortOrder },
                    set: { viewModel.sortOrder = $0 }
                ),
                onClear: { viewModel.clearFilters() }
            )

            switch viewModel.loadState {
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
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
        .background(BrightPulse.background)
    }

    private func feed(viewModel: BrowseViewModel) -> some View {
        ScrollView {
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
}
