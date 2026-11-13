import Foundation
import SerendipidCore

enum ConnectionState: Equatable {
    case idle
    case connecting
    case connected
    case failed(String)
}

@MainActor
@Observable
final class SettingsViewModel {
    var serverURLText: String = ""
    var tokenText: String = ""
    var connectionState: ConnectionState = .idle
    var isShowingScanner = false

    private let configStore: ServerConfigStore
    private let apiClient: APIClient

    init(configStore: ServerConfigStore, apiClient: APIClient) {
        self.configStore = configStore
        self.apiClient = apiClient
        serverURLText = configStore.serverURLString ?? ""
        tokenText = configStore.apiToken ?? ""
        if configStore.isConfigured {
            connectionState = .connected
        }
    }

    func connect() async {
        let trimmedURL = serverURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedToken = AccessToken.normalize(tokenText)

        guard !trimmedURL.isEmpty, URL(string: trimmedURL) != nil else {
            connectionState = .failed("Enter a valid server URL, like http://192.168.1.10:5050.")
            return
        }
        guard AccessToken.isValidFormat(normalizedToken) else {
            connectionState = .failed("The access token should be \(AccessToken.length) letters/numbers — check backend/token.txt.")
            return
        }

        connectionState = .connecting
        configStore.serverURLString = trimmedURL
        configStore.apiToken = normalizedToken
        tokenText = normalizedToken

        do {
            let _: PingResponse = try await apiClient.send(.ping)
        } catch {
            connectionState = .failed("Could not reach that server — \(error.localizedDescription)")
            return
        }

        do {
            let _: StatsResponse = try await apiClient.send(.stats)
            connectionState = .connected
        } catch {
            connectionState = .failed("Server reachable, but the access token was rejected — \(error.localizedDescription)")
        }
    }

    /// A scanned QR payload is `GET /connect-info`'s JSON shape:
    /// `{"url": "...", "token": "..."}`.
    func applyScannedPayload(_ raw: String) {
        guard let data = raw.data(using: .utf8),
              let info = try? JSONDecoder().decode(ConnectInfo.self, from: data)
        else {
            connectionState = .failed("That QR code doesn't look like a Serendipid connect code.")
            return
        }
        serverURLText = info.url
        tokenText = AccessToken.normalize(info.token)
        Task { await connect() }
    }

    func disconnect() {
        configStore.clear()
        serverURLText = ""
        tokenText = ""
        connectionState = .idle
    }
}
