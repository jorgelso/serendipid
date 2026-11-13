import SwiftUI
import SerendipidCore

/// Distinct wrapper so a thread ID doesn't collide with a post shortcode —
/// both are bare `String`s, and this stack's `navigationDestination` also
/// routes shortcodes (from `ChatSourceCardsView`'s citations) to
/// `PostDetailView`. Without this, pushing a shortcode would incorrectly
/// match the thread-ID destination closure.
struct ChatThreadRoute: Hashable {
    let threadID: String
}

struct ChatThreadListView: View {
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: ChatListViewModel?
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Chat")
            .background(BrightPulse.background)
            .navigationDestination(for: ChatThreadRoute.self) { route in
                ChatThreadView(threadID: route.threadID)
            }
            .navigationDestination(for: String.self) { shortcode in
                PostDetailView(shortcode: shortcode)
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await startNewChat(viewModel: viewModel!) }
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                }
            }
        }
        .task {
            if viewModel == nil {
                viewModel = ChatListViewModel(apiClient: apiClient)
            }
            await viewModel?.loadIfNeeded()
        }
        .onAppear {
            Task { await viewModel?.retryIfNeeded() }
        }
    }

    @ViewBuilder
    private func content(viewModel: ChatListViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            if viewModel.threads.isEmpty {
                EmptyStateView(systemImage: "bubble.left.and.bubble.right", message: "No conversations yet.")
            } else {
                List {
                    ForEach(viewModel.threads) { thread in
                        NavigationLink(value: ChatThreadRoute(threadID: thread.id)) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(thread.title?.isEmpty == false ? thread.title! : "New conversation")
                                    .font(BrightPulseFont.body(size: 15, weight: .semibold))
                                    .foregroundStyle(BrightPulse.ink)
                            }
                        }
                    }
                    .onDelete { offsets in
                        Task {
                            for index in offsets {
                                await viewModel.deleteThread(viewModel.threads[index])
                            }
                        }
                    }
                }
                .listStyle(.plain)
                .refreshable {
                    await viewModel.refresh()
                }
            }
        }
    }

    private func startNewChat(viewModel: ChatListViewModel) async {
        if let thread = await viewModel.createThread() {
            path.append(ChatThreadRoute(threadID: thread.id))
        }
    }
}
