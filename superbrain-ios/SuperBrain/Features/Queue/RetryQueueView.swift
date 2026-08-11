import SwiftUI
import SuperBrainCore

/// Two distinct "things waiting to happen" surfaces, kept on one screen
/// since both answer the same question ("did my save actually go through?"):
/// - **Waiting to send** — shares the Share Extension queued locally because
///   the backend was unreachable (`PendingShareStore`); nothing was ever
///   sent.
/// - **Server retry queue** — items the backend *did* receive but hit a
///   quota/rate-limit exhaustion on, so it scheduled them for automatic
///   retry itself (`GET /queue/retry`).
struct RetryQueueView: View {
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: RetryQueueViewModel?

    var body: some View {
        Group {
            if let viewModel {
                content(viewModel: viewModel)
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Sync & Retry")
        .navigationBarTitleDisplayMode(.inline)
        .background(BrightPulse.background)
        .task {
            if viewModel == nil {
                viewModel = RetryQueueViewModel(apiClient: apiClient)
            }
            await viewModel?.loadIfNeeded()
        }
    }

    @ViewBuilder
    private func content(viewModel: RetryQueueViewModel) -> some View {
        switch viewModel.loadState {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            EmptyStateView(systemImage: "wifi.slash", message: message)
        case .loaded:
            if viewModel.pendingShares.isEmpty && viewModel.retryItems.isEmpty {
                EmptyStateView(systemImage: "checkmark.circle", message: "Nothing waiting — everything you've saved has reached the server.")
            } else {
                List {
                    if let status = viewModel.status {
                        Section {
                            statusSummary(status)
                        }
                    }
                    if !viewModel.pendingShares.isEmpty {
                        pendingSection(viewModel: viewModel)
                    }
                    if !viewModel.retryItems.isEmpty {
                        retrySection(viewModel: viewModel)
                    }
                }
                .listStyle(.insetGrouped)
                .refreshable { await viewModel.refresh() }
            }
        }
    }

    private func statusSummary(_ status: QueueStatusResponse) -> some View {
        HStack {
            summaryStat(count: status.processing_count, label: "processing")
            Spacer()
            summaryStat(count: status.queue_count, label: "queued")
            Spacer()
            summaryStat(count: status.retry_count, label: "retrying")
        }
    }

    private func summaryStat(count: Int, label: String) -> some View {
        VStack(spacing: 2) {
            Text("\(count)")
                .font(BrightPulseFont.display(size: 18, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
            Text(label)
                .font(BrightPulseFont.body(size: 11))
                .foregroundStyle(BrightPulse.inkMuted)
        }
        .frame(maxWidth: .infinity)
    }

    private func pendingSection(viewModel: RetryQueueViewModel) -> some View {
        Section {
            ForEach(viewModel.pendingShares) { share in
                PendingShareRow(share: share)
                    .swipeActions {
                        Button("Cancel", role: .destructive) {
                            viewModel.cancelPendingShare(share)
                        }
                    }
            }
        } header: {
            Text("Waiting to send")
        } footer: {
            Text("Never reached the server — couldn't connect when you shared these. Synced automatically when the app is opened, or tap below to try now.")
        }

        Section {
            Button {
                Task { await viewModel.syncPendingSharesNow() }
            } label: {
                HStack {
                    if viewModel.isSyncing {
                        ProgressView().tint(BrightPulse.coralInk)
                    }
                    Text(viewModel.isSyncing ? "Syncing…" : "Sync now")
                }
            }
            .disabled(viewModel.isSyncing)
        }
    }

    private func retrySection(viewModel: RetryQueueViewModel) -> some View {
        Section {
            ForEach(viewModel.retryItems) { item in
                RetryItemRow(item: item)
                    .swipeActions {
                        Button("Remove", role: .destructive) {
                            Task { await viewModel.deleteRetryItem(item) }
                        }
                    }
            }
        } header: {
            Text("Server retry queue")
        } footer: {
            Text("The server received these but hit a rate limit or quota, so it scheduled them to retry on its own. Force retry to promote them right away.")
        }

        Section {
            Button {
                Task { await viewModel.forceRetryAll() }
            } label: {
                HStack {
                    if viewModel.isFlushing {
                        ProgressView().tint(BrightPulse.coralInk)
                    }
                    Text(viewModel.isFlushing ? "Retrying…" : "Force retry all")
                }
            }
            .disabled(viewModel.isFlushing)
        }
    }
}

private struct PendingShareRow: View {
    let share: PendingShare

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(share.url)
                .font(BrightPulseFont.body(size: 13, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
                .lineLimit(1)
            Text("Shared \(RelativeDateFormatting.string(from: share.createdAt))")
                .font(BrightPulseFont.body(size: 11))
                .foregroundStyle(BrightPulse.inkMuted)
        }
        .padding(.vertical, 2)
    }
}

private struct RetryItemRow: View {
    let item: RetryQueueItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.url)
                .font(BrightPulseFont.body(size: 13, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
                .lineLimit(1)
            HStack(spacing: 6) {
                if let reason = item.reason, !reason.isEmpty {
                    Text(reason)
                        .font(BrightPulseFont.body(size: 11))
                        .foregroundStyle(BrightPulse.yellowInk)
                }
                if let attempts = item.attempts {
                    Text("· attempt \(attempts)")
                        .font(BrightPulseFont.body(size: 11))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                if let retryAfter = item.retry_after, let date = RelativeDateFormatting.parseBackendTimestamp(retryAfter) {
                    Text("· retries \(RelativeDateFormatting.string(from: date))")
                        .font(BrightPulseFont.body(size: 11))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

/// The backend stamps timestamps with Python's `datetime.utcnow().isoformat()`
/// — no timezone suffix, implicitly UTC. `ISO8601DateFormatter` requires an
/// explicit offset by default, so this parses it as UTC explicitly rather
/// than silently misreading it as local time.
enum RelativeDateFormatting {
    private static let backendFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    private static let backendFormatterNoFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    static func parseBackendTimestamp(_ raw: String) -> Date? {
        let withOffset = raw.hasSuffix("Z") ? raw : raw + "Z"
        return backendFormatter.date(from: withOffset) ?? backendFormatterNoFraction.date(from: withOffset)
    }

    static func string(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

#Preview {
    NavigationStack {
        RetryQueueView()
    }
}
