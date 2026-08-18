import SwiftUI
import SuperBrainCore

struct SettingsView: View {
    @Environment(\.configStore) private var configStore
    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: SettingsViewModel?
    @State private var pendingShareCount = 0
    @AppStorage("chatAlwaysShowSources") private var alwaysShowSources = false

    var body: some View {
        NavigationStack {
            Group {
                if let viewModel {
                    content(viewModel: viewModel)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("Settings")
            .background(BrightPulse.background)
        }
        .task {
            if viewModel == nil {
                viewModel = SettingsViewModel(configStore: configStore, apiClient: apiClient)
            }
        }
        .onAppear {
            pendingShareCount = PendingShareStore().count
        }
    }

    @ViewBuilder
    private func content(viewModel: SettingsViewModel) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                connectionCard(viewModel: viewModel)
                statusView(viewModel: viewModel)

                if viewModel.connectionState == .connected {
                    syncRow
                    versionsRow
                    preferencesCard
                    PillButton("Disconnect", style: .secondary) {
                        viewModel.disconnect()
                    }
                }
            }
            .padding(20)
        }
        .sheet(isPresented: Binding(
            get: { viewModel.isShowingScanner },
            set: { viewModel.isShowingScanner = $0 }
        )) {
            NavigationStack {
                QRScannerView { payload in
                    viewModel.applyScannedPayload(payload)
                }
            }
        }
    }

    private var syncRow: some View {
        NavigationLink {
            RetryQueueView()
        } label: {
            Card {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Sync & Retry")
                            .font(BrightPulseFont.body(size: 15, weight: .semibold))
                            .foregroundStyle(BrightPulse.ink)
                        if pendingShareCount > 0 {
                            Text("\(pendingShareCount) save\(pendingShareCount == 1 ? "" : "s") waiting to send")
                                .font(BrightPulseFont.body(size: 12))
                                .foregroundStyle(BrightPulse.yellowInk)
                        } else {
                            Text("Everything you've shared has reached the server")
                                .font(BrightPulseFont.body(size: 12))
                                .foregroundStyle(BrightPulse.inkMuted)
                        }
                    }
                    Spacer()
                    if pendingShareCount > 0 {
                        Text("\(pendingShareCount)")
                            .font(BrightPulseFont.body(size: 12, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Capsule().fill(BrightPulse.coral))
                    }
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                .padding(16)
            }
        }
        .buttonStyle(.plain)
    }

    private var versionsRow: some View {
        NavigationLink {
            VersionsView()
        } label: {
            Card {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Analysis versions")
                            .font(BrightPulseFont.body(size: 15, weight: .semibold))
                            .foregroundStyle(BrightPulse.ink)
                        Text("Pipeline changelog & bulk rescan for stale posts")
                            .font(BrightPulseFont.body(size: 12))
                            .foregroundStyle(BrightPulse.inkMuted)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                .padding(16)
            }
        }
        .buttonStyle(.plain)
    }

    private var preferencesCard: some View {
        Card {
            Toggle(isOn: $alwaysShowSources) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Always show chat sources")
                        .font(BrightPulseFont.body(size: 15, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                    Text("Off shows a \"Show sources\" toggle per answer instead")
                        .font(BrightPulseFont.body(size: 12))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
            }
            .tint(BrightPulse.coral)
            .padding(16)
        }
    }

    private func connectionCard(viewModel: SettingsViewModel) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Connection")
                        .font(BrightPulseFont.display(size: 18, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                    Spacer()
                    Button {
                        viewModel.isShowingScanner = true
                    } label: {
                        Image(systemName: "qrcode.viewfinder")
                            .foregroundStyle(BrightPulse.coral)
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Server URL")
                        .font(BrightPulseFont.body(size: 13, weight: .semibold))
                        .foregroundStyle(BrightPulse.inkMuted)
                    TextField("e.g. http://192.168.1.10:5000", text: Binding(
                        get: { viewModel.serverURLText },
                        set: { viewModel.serverURLText = $0 }
                    ))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .padding(12)
                    .background(BrightPulse.surface2)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Access Token")
                        .font(BrightPulseFont.body(size: 13, weight: .semibold))
                        .foregroundStyle(BrightPulse.inkMuted)
                    TokenEntryField(token: Binding(
                        get: { viewModel.tokenText },
                        set: { viewModel.tokenText = $0 }
                    ))
                }

                PillButton(
                    viewModel.connectionState == .connecting ? "Connecting…" : "Connect",
                    isLoading: viewModel.connectionState == .connecting
                ) {
                    Task { await viewModel.connect() }
                }
            }
            .padding(20)
        }
    }

    @ViewBuilder
    private func statusView(viewModel: SettingsViewModel) -> some View {
        switch viewModel.connectionState {
        case .idle, .connecting:
            EmptyView()
        case .connected:
            Label("Connected", systemImage: "checkmark.circle.fill")
                .foregroundStyle(BrightPulse.mintInk)
                .font(BrightPulseFont.body(size: 14, weight: .semibold))
        case .failed(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(BrightPulse.danger)
                .font(BrightPulseFont.body(size: 13))
        }
    }
}

#Preview {
    SettingsView()
}
