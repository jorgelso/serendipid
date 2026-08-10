import SwiftUI
import SuperBrainCore

@main
struct SuperBrainApp: App {
    private let configStore: ServerConfigStore
    private let apiClient: APIClient
    private let dataStore: AppDataStore

    init() {
        let configStore = ServerConfigStore()
        self.configStore = configStore
        self.apiClient = APIClient(configStore: configStore)
        self.dataStore = AppDataStore(client: apiClient)
    }

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(\.configStore, configStore)
                .environment(\.apiClient, apiClient)
                .environment(dataStore)
        }
    }
}
