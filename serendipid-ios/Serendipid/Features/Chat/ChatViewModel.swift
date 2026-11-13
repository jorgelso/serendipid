import Foundation
import SerendipidCore

@MainActor
@Observable
final class ChatListViewModel {
    private let apiClient: APIClient

    var loadState: LoadState = .idle
    var threads: [ChatThread] = []

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await refresh()
    }

    /// See `HomeViewModel.retryIfNeeded`.
    func retryIfNeeded() async {
        switch loadState {
        case .loaded, .loading:
            return
        case .idle, .error:
            await refresh()
        }
    }

    func refresh() async {
        loadState = .loading
        do {
            let response: ChatThreadsResponse = try await apiClient.send(.chatThreads)
            threads = response.data.sorted { $0.updated_at > $1.updated_at }
            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    func createThread() async -> ChatThread? {
        do {
            let response: ChatThreadCreateResponse = try await apiClient.send(.chatThreadCreate, body: EmptyBody())
            threads.insert(response.data, at: 0)
            return response.data
        } catch {
            loadState = .error(error.localizedDescription)
            return nil
        }
    }

    func deleteThread(_ thread: ChatThread) async {
        threads.removeAll { $0.id == thread.id }
        let _: ChatThreadDeleteResponse? = try? await apiClient.send(.chatThreadDelete(id: thread.id))
    }
}

@MainActor
@Observable
final class ChatThreadViewModel {
    let threadID: String
    private let apiClient: APIClient

    var loadState: LoadState = .idle
    var messages: [ChatMessage] = []
    var draft: String = ""
    var isSending = false

    init(threadID: String, apiClient: APIClient) {
        self.threadID = threadID
        self.apiClient = apiClient
    }

    func loadIfNeeded() async {
        guard loadState == .idle else { return }
        await load()
    }

    func load() async {
        loadState = .loading
        do {
            let response: ChatThreadDetailResponse = try await apiClient.send(.chatThread(id: threadID))
            messages = response.data.messages
            loadState = .loaded
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }

    func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        draft = ""
        isSending = true
        do {
            let response: ChatMessageExchangeResponse = try await apiClient.send(
                .chatMessages(threadID: threadID),
                body: ChatMessageRequest(message: text)
            )
            messages.append(response.data.user_message)
            messages.append(response.data.assistant_message)
        } catch {
            loadState = .error((error as? APIError)?.errorDescription ?? error.localizedDescription)
        }
        isSending = false
    }
}

/// `POST /chat/threads` takes an empty JSON body.
struct EmptyBody: Encodable {}
