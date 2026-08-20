import SwiftUI
import SuperBrainCore

struct PostDetailView: View {
    let shortcode: String

    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: PostDetailViewModel?
    @State private var isShowingEditSheet = false

    var body: some View {
        Group {
            if let viewModel {
                content(viewModel: viewModel)
            } else {
                ProgressView()
            }
        }
        .background(BrightPulse.background)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if viewModel?.post != nil {
                ToolbarItem(placement: .primaryAction) {
                    Button("Edit") { isShowingEditSheet = true }
                }
            }
        }
        .sheet(isPresented: $isShowingEditSheet) {
            if let post = viewModel?.post {
                EditPostSheet(post: post) {
                    await viewModel?.reload()
                }
            }
        }
        .task {
            if viewModel == nil {
                viewModel = PostDetailViewModel(shortcode: shortcode, dataStore: dataStore, configStore: configStore)
            }
            await viewModel?.loadIfNeeded()
        }
        .task(id: shortcode) {
            // A "qualifying view" — long enough to count as genuine interest,
            // not just a bounce — mirrors the web app's useQualifyingView
            // hook (20s dwell for a non-video open). Cancelled automatically
            // if the user navigates away before this fires.
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            guard !Task.isCancelled else { return }
            await dataStore.logView(shortcode: shortcode)
        }
    }

    @ViewBuilder
    private func content(viewModel: PostDetailViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "exclamationmark.triangle", message: message)
        case .loaded:
            if let post = viewModel.post {
                detail(post: post, viewModel: viewModel)
            }
        }
    }

    private func detail(post: Post, viewModel: PostDetailViewModel) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                MediaViewer(post: post, baseURL: viewModel.baseURL) {
                    Task {
                        await ReanalyzeService.reanalyze(url: post.url, apiClient: apiClient)
                        await viewModel.reload()
                    }
                }

                Text(post.title?.isEmpty == false ? post.title! : "Untitled reel")
                    .font(BrightPulseFont.display(size: 22, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)

                Text("@\(post.username)")
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)

                badgeRow(post: post)

                RatingControlsView(post: post) {
                    await viewModel.reload()
                }

                if let summary = post.summary, !summary.isEmpty {
                    Text(summary)
                        .font(BrightPulseFont.body(size: 15))
                        .foregroundStyle(BrightPulse.ink)
                }

                if !post.tags.isEmpty {
                    tagWrap(post: post)
                }

                FullAnalysisDisclosure(post: post)

                if post.needs_review {
                    ReviewActionsView(post: post) {
                        await viewModel.reload()
                    }
                }

                if !viewModel.relatedPosts.isEmpty {
                    relatedSection(viewModel: viewModel)
                }
            }
            .padding(16)
        }
    }

    private func badgeRow(post: Post) -> some View {
        HStack(spacing: 6) {
            ForEach(post.category, id: \.self) { category in
                LabelPill(category)
            }
            ForEach(post.language, id: \.self) { language in
                PillBadge("🌐 \(language)", background: BrightPulse.surface2, foreground: BrightPulse.inkMuted, uppercase: false)
            }
            if let importanceBadge = ImportanceBadge(importance: post.importance) {
                importanceBadge
            }
            if post.is_eloquent == 1 {
                PillBadge(
                    post.is_tutorial == 1 ? "🎙 tutorial" : "🎙 eloquent",
                    background: BrightPulse.tealSoft, foreground: BrightPulse.tealInk, uppercase: false
                )
            }
        }
    }

    private func tagWrap(post: Post) -> some View {
        FlowLayout(spacing: 6) {
            ForEach(post.tags, id: \.self) { tag in
                LabelPill(tag, uppercase: false)
            }
        }
    }

    private func relatedSection(viewModel: PostDetailViewModel) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Related")
                .font(BrightPulseFont.display(size: 16, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(viewModel.relatedPosts) { related in
                        NavigationLink(value: related.post.shortcode) {
                            PostCardView(post: related.post, baseURL: viewModel.baseURL, similarity: Double(related.similarity))
                                .frame(width: 220)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

/// Simple wrapping tag layout — SwiftUI's `Layout` protocol, iOS 16+.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var totalHeight: CGFloat = 0
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if rowWidth + size.width > width, rowWidth > 0 {
                totalHeight += rowHeight + spacing
                rowWidth = 0
                rowHeight = 0
            }
            rowWidth += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        totalHeight += rowHeight
        return CGSize(width: width, height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
