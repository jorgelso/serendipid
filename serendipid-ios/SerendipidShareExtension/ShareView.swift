import SwiftUI
import SerendipidCore

struct ShareView: View {
    let extensionContext: NSExtensionContext?
    @State private var viewModel = ShareViewModel()

    var body: some View {
        VStack(spacing: 20) {
            Text("Serendipid")
                .font(BrightPulseFont.display(size: 20, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)

            content

            Button("Cancel") {
                viewModel.cancel(extensionContext: extensionContext)
            }
            .font(BrightPulseFont.body(size: 14))
            .foregroundStyle(BrightPulse.inkMuted)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(BrightPulse.background)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .padding(20)
        .task {
            await viewModel.start(extensionContext: extensionContext)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loadingURL:
            ProgressView()

        case .notConfigured:
            Text("Open Serendipid and connect to a server first.")
                .font(BrightPulseFont.body(size: 14))
                .foregroundStyle(BrightPulse.inkMuted)
                .multilineTextAlignment(.center)

        case .ready(let preview):
            VStack(spacing: 16) {
                VStack(spacing: 4) {
                    Text(preview ?? viewModel.sharedURL ?? "")
                        .font(BrightPulseFont.body(size: 14, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                    if preview != nil, let url = viewModel.sharedURL {
                        Text(url)
                            .font(BrightPulseFont.body(size: 11))
                            .foregroundStyle(BrightPulse.inkMuted)
                            .lineLimit(1)
                    }
                }

                if !viewModel.collections.isEmpty {
                    collectionPicker
                }

                PillButton("Save") {
                    Task { await viewModel.save(extensionContext: extensionContext) }
                }
            }

        case .saving:
            VStack(spacing: 10) {
                ProgressView()
                Text("Saving…")
                    .font(BrightPulseFont.body(size: 14))
                    .foregroundStyle(BrightPulse.inkMuted)
            }

        case .success:
            VStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(BrightPulse.mintInk)
                Text("Saved")
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
            }

        case .queuedOffline:
            VStack(spacing: 10) {
                Image(systemName: "tray.and.arrow.down.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(BrightPulse.yellowInk)
                Text("Saved offline")
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
                Text("Couldn't reach your Serendipid server — this will send automatically once the app is back online.")
                    .font(BrightPulseFont.body(size: 12))
                    .foregroundStyle(BrightPulse.inkMuted)
                    .multilineTextAlignment(.center)
            }

        case .failure(let message):
            VStack(spacing: 12) {
                Text(message)
                    .font(BrightPulseFont.body(size: 13))
                    .foregroundStyle(BrightPulse.danger)
                    .multilineTextAlignment(.center)
                PillButton("Try Again", style: .secondary) {
                    Task { await viewModel.save(extensionContext: extensionContext) }
                }
            }
        }
    }

    private var collectionPicker: some View {
        Menu {
            Button("None") { viewModel.selectedCollectionID = nil }
            ForEach(viewModel.collections) { collection in
                Button(collection.name) { viewModel.selectedCollectionID = collection.id }
            }
        } label: {
            HStack {
                Text(viewModel.collections.first { $0.id == viewModel.selectedCollectionID }?.name ?? "Add to collection…")
                Image(systemName: "chevron.down")
            }
            .font(BrightPulseFont.body(size: 13, weight: .semibold))
            .foregroundStyle(BrightPulse.ink)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Capsule().fill(BrightPulse.surface2))
        }
    }
}
