import SwiftUI
import SuperBrainCore

struct SearchView: View {
    @Environment(\.apiClient) private var apiClient
    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @State private var viewModel: SearchViewModel?

    var body: some View {
        NavigationStack {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Search")
            .background(BrightPulse.background)
            .navigationDestination(for: String.self) { shortcode in
                PostDetailView(shortcode: shortcode)
            }
        }
        .task {
            if viewModel == nil {
                viewModel = SearchViewModel(apiClient: apiClient, dataStore: dataStore, configStore: configStore)
            }
        }
    }

    @ViewBuilder
    private func content(viewModel: SearchViewModel) -> some View {
        VStack(spacing: 0) {
            searchBar(viewModel: viewModel)

            switch viewModel.loadState {
            case .idle:
                EmptyStateView(
                    systemImage: "sparkle.magnifyingglass",
                    message: "Type an interest above — an instrument, a recipe, a mindset — and see what you've already saved about it."
                )
            case .loading:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            case .error(let message):
                EmptyStateView(systemImage: "wifi.slash", message: message)
            case .loaded:
                if viewModel.hits.isEmpty {
                    EmptyStateView(
                        systemImage: "questionmark.circle",
                        message: "Nothing matched \"\(viewModel.query)\" closely enough. Try a broader phrase."
                    )
                } else {
                    results(viewModel: viewModel)
                }
            }
        }
        .background(BrightPulse.background)
    }

    private func searchBar(viewModel: SearchViewModel) -> some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(BrightPulse.inkMuted)
            TextField("Search what you've saved…", text: Binding(
                get: { viewModel.query },
                set: {
                    viewModel.query = $0
                    viewModel.onQueryChanged()
                }
            ))
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
        }
        .padding(12)
        .background(BrightPulse.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .padding(16)
    }

    private func results(viewModel: SearchViewModel) -> some View {
        ScrollView {
            LazyVStack(spacing: 16) {
                ForEach(viewModel.hits) { hit in
                    NavigationLink(value: hit.shortcode) {
                        PostCardView(post: viewModel.mergedPost(for: hit), baseURL: viewModel.baseURL, similarity: hit.similarity)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
    }
}
