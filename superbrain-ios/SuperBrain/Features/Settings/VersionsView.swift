import SwiftUI
import SuperBrainCore

/// Pipeline changelog + bulk "rescan a whole stale cohort" — ports the web
/// app's `/versions` screen (`VersionPager`/`VersionPanel`), collapsed into
/// one scrolling list rather than a horizontal pager (there's usually only a
/// handful of versions represented in one person's library at a time).
struct VersionsView: View {
    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: VersionsViewModel?

    var body: some View {
        Group {
            if let viewModel {
                content(viewModel: viewModel)
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Analysis versions")
        .navigationBarTitleDisplayMode(.inline)
        .background(BrightPulse.background)
        .task {
            if viewModel == nil {
                viewModel = VersionsViewModel(dataStore: dataStore, apiClient: apiClient)
            }
            await viewModel?.loadIfNeeded()
        }
    }

    @ViewBuilder
    private func content(viewModel: VersionsViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            List {
                if !viewModel.staleGroups.isEmpty {
                    Section {
                        ForEach(viewModel.staleGroups) { group in
                            staleGroupRow(group, viewModel: viewModel)
                        }
                    } header: {
                        Text("Stale posts")
                    } footer: {
                        Text("These posts were analyzed under an older pipeline version. Rescan a cohort to bring it up to date.")
                    }
                } else {
                    Section {
                        Label("Every post is up to date.", systemImage: "checkmark.circle")
                            .foregroundStyle(BrightPulse.mintInk)
                    }
                }

                Section("Changelog") {
                    ForEach(viewModel.history) { entry in
                        changelogRow(entry, isCurrent: entry.version == viewModel.currentVersion)
                    }
                }
            }
            .listStyle(.insetGrouped)
            .refreshable { await viewModel.refresh() }
        }
    }

    private func staleGroupRow(_ group: StaleVersionGroup, viewModel: VersionsViewModel) -> some View {
        let isRescanning = viewModel.rescanningVersion == group.version
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Version \(group.version)")
                        .font(BrightPulseFont.body(size: 14, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                    Text("\(group.shortcodes.count) post\(group.shortcodes.count == 1 ? "" : "s")")
                        .font(BrightPulseFont.body(size: 12))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                Spacer()
                if let currentVersion = viewModel.currentVersion {
                    VersionBehindBadge(versionsBehind: currentVersion - group.version)
                }
            }

            PillButton(
                isRescanning ? "Rescanning…" : "Rescan all",
                style: .secondary,
                isLoading: isRescanning
            ) {
                Task { await viewModel.rescan(group) }
            }
            .disabled(viewModel.rescanningVersion != nil)
        }
        .padding(.vertical, 4)
    }

    private func changelogRow(_ entry: ChangelogEntry, isCurrent: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("v\(entry.version) — \(entry.title)")
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
                if isCurrent {
                    PillBadge("current", background: BrightPulse.mintSoft, foreground: BrightPulse.mintInk)
                }
            }
            if !entry.description.isEmpty {
                Text(entry.description)
                    .font(BrightPulseFont.body(size: 13))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
        .padding(.vertical, 2)
    }
}

#Preview {
    NavigationStack {
        VersionsView()
    }
}
