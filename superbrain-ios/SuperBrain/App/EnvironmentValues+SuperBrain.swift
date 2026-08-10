import SwiftUI
import SuperBrainCore

// `ServerConfigStore` (a plain class) and `APIClient` (an actor) aren't
// `@Observable`, so SwiftUI's typed `environment(_:)` overload doesn't apply
// to them the way it does to `AppDataStore` — custom `EnvironmentKey`s carry
// them instead. Every screen is expected to run inside `SuperBrainApp`'s
// injected environment, so a missing injection (a bug, not a real runtime
// state) falls back to a fresh, harmless instance rather than crashing.

private struct ServerConfigStoreKey: EnvironmentKey {
    static let defaultValue = ServerConfigStore()
}

private struct APIClientKey: EnvironmentKey {
    static let defaultValue = APIClient(configStore: ServerConfigStore())
}

extension EnvironmentValues {
    var configStore: ServerConfigStore {
        get { self[ServerConfigStoreKey.self] }
        set { self[ServerConfigStoreKey.self] = newValue }
    }

    var apiClient: APIClient {
        get { self[APIClientKey.self] }
        set { self[APIClientKey.self] = newValue }
    }
}
