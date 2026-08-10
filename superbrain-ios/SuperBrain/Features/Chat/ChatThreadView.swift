import SwiftUI
import SuperBrainCore

struct ChatThreadView: View {
    let threadID: String

    @Environment(\.apiClient) private var apiClient
    @State private var viewModel: ChatThreadViewModel?

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
        .task {
            if viewModel == nil {
                viewModel = ChatThreadViewModel(threadID: threadID, apiClient: apiClient)
            }
            await viewModel?.loadIfNeeded()
        }
    }

    @ViewBuilder
    private func content(viewModel: ChatThreadViewModel) -> some View {
        VStack(spacing: 0) {
            switch viewModel.loadState {
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            case .error(let message):
                EmptyStateView(systemImage: "wifi.slash", message: message)
            case .loaded:
                messageList(viewModel: viewModel)
            }

            inputBar(viewModel: viewModel)
        }
    }

    private func messageList(viewModel: ChatThreadViewModel) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                if viewModel.messages.isEmpty {
                    EmptyStateView(
                        systemImage: "sparkles",
                        message: "Ask about anything you've saved — a topic, a technique, a place — and I'll answer from what you've actually saved, with sources."
                    )
                    .padding(.top, 60)
                } else {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        ForEach(viewModel.messages) { message in
                            ChatMessageBubbleView(message: message)
                                .id(message.id)
                        }
                        if viewModel.isSending {
                            TypingIndicatorView()
                        }
                    }
                    .padding(16)
                }
            }
            .onChange(of: viewModel.messages.count) {
                if let last = viewModel.messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func inputBar(viewModel: ChatThreadViewModel) -> some View {
        HStack(spacing: 10) {
            TextField("Ask something…", text: Binding(
                get: { viewModel.draft },
                set: { viewModel.draft = $0 }
            ), axis: .vertical)
                .lineLimit(1...4)
                .padding(10)
                .background(BrightPulse.surface2)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            Button {
                Task { await viewModel.send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(viewModel.draft.trimmingCharacters(in: .whitespaces).isEmpty ? BrightPulse.inkMuted : BrightPulse.coral)
            }
            .disabled(viewModel.draft.trimmingCharacters(in: .whitespaces).isEmpty || viewModel.isSending)
        }
        .padding(12)
        .background(BrightPulse.surface)
    }
}

private struct ChatMessageBubbleView: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 40) }

            VStack(alignment: .leading, spacing: 8) {
                if message.role == .assistant {
                    Text(LocalizedStringKey(message.content))
                        .font(BrightPulseFont.body(size: 14))
                        .foregroundStyle(BrightPulse.ink)
                    ChatSourceCardsView(sources: message.sources)
                } else {
                    Text(message.content)
                        .font(BrightPulseFont.body(size: 14))
                        .foregroundStyle(.white)
                }
            }
            .padding(12)
            .background(message.role == .user ? BrightPulse.coral : BrightPulse.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            if message.role == .assistant { Spacer(minLength: 40) }
        }
    }
}

private struct TypingIndicatorView: View {
    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(BrightPulse.inkMuted)
                    .frame(width: 6, height: 6)
            }
        }
        .padding(12)
        .background(BrightPulse.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
