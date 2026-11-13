import SwiftUI
import SerendipidCore

/// The 3D "vector space" tab — every saved post plotted by embedding
/// similarity (`VectorSpaceProjection`, dual PCA over embeddings) and
/// colored by which AI-noticed theme it belongs to
/// (`ThemeClustering.computeThemes`, not re-run here). Mirrors the web app's
/// `/space` view in spirit (`serendipid-web/src/app/space/page.tsx`) but
/// with native SceneKit orbit/pan/pinch instead of react-three-fiber.
struct SpaceView: View {
    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: SpaceViewModel?
    @State private var selectedPoint: VectorSpacePoint?
    @State private var resetSignal = 0

    var body: some View {
        Group {
            if let viewModel {
                content(viewModel: viewModel)
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Space")
        .navigationBarTitleDisplayMode(.inline)
        .background(BrightPulse.background)
        .navigationDestination(for: String.self) { shortcode in
            PostDetailView(shortcode: shortcode)
        }
        .task {
            if viewModel == nil {
                viewModel = SpaceViewModel(dataStore: dataStore, configStore: configStore, apiClient: apiClient)
            }
            await viewModel?.loadIfNeeded()
        }
        .onAppear {
            Task { await viewModel?.retryIfNeeded() }
        }
        .toolbar {
            // A SceneKit canvas can't host a pull-to-refresh gesture (it
            // would fight the scene's own pan/orbit gestures), so this is a
            // manual equivalent instead.
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await viewModel?.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
    }

    @ViewBuilder
    private func content(viewModel: SpaceViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            if viewModel.points.count < SpaceViewModel.minPointsForMeaningfulLayout {
                EmptyStateView(
                    systemImage: "circle.hexagongrid",
                    message: "Analyze at least a few more reels to see them laid out in 3D — the vector space needs a handful of embedded posts before the layout means anything."
                )
            } else {
                scene(viewModel: viewModel)
            }
        }
    }

    private func scene(viewModel: SpaceViewModel) -> some View {
        ZStack(alignment: .top) {
            SceneKitVectorSpaceView(
                points: viewModel.points,
                resetSignal: resetSignal,
                highlightedShortcodes: viewModel.highlightedShortcodes
            ) { point in
                selectedPoint = point
            }
            .ignoresSafeArea(edges: .bottom)

            VStack(alignment: .leading, spacing: 8) {
                SpaceSearchBar(viewModel: viewModel)
                    .padding(.horizontal, 12)

                HStack(alignment: .top) {
                    LegendView(
                        entries: viewModel.legendEntries,
                        selectedColorSlot: viewModel.legendSelection,
                        onSelect: { viewModel.toggleLegendSelection($0) }
                    )
                    Spacer()
                    Button {
                        selectedPoint = nil
                        resetSignal += 1
                    } label: {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(10)
                            .background(Circle().fill(.black.opacity(0.45)))
                    }
                    .padding(.trailing, 12)
                }
            }
            .padding(.top, 12)

            if let selectedPoint {
                VStack {
                    Spacer()
                    SelectedPointCard(point: selectedPoint, baseURL: viewModel.baseURL) {
                        self.selectedPoint = nil
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 16)
                }
            }
        }
    }
}

/// Free-text box that runs the same semantic search as the Search tab
/// (`GET /search/semantic`) and lights up the matched shortcodes in the
/// scene — mirrors the web app's `VectorSpaceSearch.tsx` ("Light up reels
/// about…"), including that starting a search clears any active legend
/// selection (see `SpaceViewModel.onSearchQueryChanged`).
private struct SpaceSearchBar: View {
    let viewModel: SpaceViewModel

    var body: some View {
        HStack(spacing: 8) {
            Text("✦")
                .foregroundStyle(.white.opacity(0.6))

            TextField(
                "",
                text: Binding(
                    get: { viewModel.searchQuery },
                    set: {
                        viewModel.searchQuery = $0
                        viewModel.onSearchQueryChanged()
                    }
                ),
                prompt: Text("Light up reels about…").foregroundStyle(.white.opacity(0.5))
            )
            .foregroundStyle(.white)
            .font(BrightPulseFont.body(size: 13, weight: .semibold))
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()

            if viewModel.isSearching {
                Text("…")
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(.white.opacity(0.6))
            } else if !viewModel.searchQuery.isEmpty {
                Button {
                    viewModel.clearHighlight()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.white.opacity(0.6))
                }
            }

            if let searchError = viewModel.searchError {
                Text(searchError)
                    .font(BrightPulseFont.body(size: 11))
                    .foregroundStyle(BrightPulse.coral)
                    .lineLimit(1)
            } else if let count = viewModel.searchResultShortcodes?.count {
                Text("\(count)")
                    .font(BrightPulseFont.body(size: 11))
                    .foregroundStyle(.white.opacity(0.6))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .frame(maxWidth: 280, alignment: .leading)
    }
}

private struct LegendView: View {
    let entries: [(colorSlot: VectorSpaceColorSlot, label: String)]
    let selectedColorSlot: VectorSpaceColorSlot?
    let onSelect: (VectorSpaceColorSlot) -> Void

    var body: some View {
        if !entries.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    let isSelected = selectedColorSlot == entry.colorSlot
                    Button {
                        onSelect(entry.colorSlot)
                    } label: {
                        HStack(spacing: 6) {
                            Circle()
                                .fill(SpacePalette.color(for: entry.colorSlot))
                                .frame(width: 8, height: 8)
                            Text(entry.label)
                                .font(BrightPulseFont.body(size: 11, weight: .semibold))
                                .foregroundStyle(.white)
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 6)
                        .padding(.vertical, 4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .fill(isSelected ? .white.opacity(0.2) : .clear)
                        )
                    }
                    .buttonStyle(.plain)
                }

                if selectedColorSlot != nil {
                    Button("Show all") {
                        onSelect(selectedColorSlot!)
                    }
                    .font(BrightPulseFont.body(size: 11, weight: .semibold))
                    .foregroundStyle(BrightPulse.coral)
                    .padding(.horizontal, 6)
                    .padding(.top, 4)
                }
            }
            .padding(6)
            .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .padding(.leading, 12)
            .frame(maxWidth: 170, alignment: .leading)
        }
    }
}

private struct SelectedPointCard: View {
    let point: VectorSpacePoint
    let baseURL: URL?
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            ResolvedThumbnailImage(raw: point.thumbnail, baseURL: baseURL)
                .aspectRatio(contentMode: .fill)
                .frame(width: 56, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            VStack(alignment: .leading, spacing: 3) {
                Text(point.title?.isEmpty == false ? point.title! : "Untitled reel")
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
                    .lineLimit(1)
                Text(point.themeLabel)
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(BrightPulse.inkMuted)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            NavigationLink(value: point.shortcode) {
                Text("Open")
                    .font(BrightPulseFont.body(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(BrightPulse.coral))
            }

            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(BrightPulse.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(BrightPulse.line, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.2), radius: 12, x: 0, y: 6)
    }
}
