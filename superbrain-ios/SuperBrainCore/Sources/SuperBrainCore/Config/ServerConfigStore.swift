import Foundation
import Security

/// Single source of truth for the backend server URL + API token, shared
/// between the main app and the Share Extension via an App Group (for the
/// non-secret URL) and the shared Keychain access group (for the secret
/// token) — neither target should touch `UserDefaults.standard` or the
/// Keychain directly for this data.
///
/// Both targets' entitlements list exactly one custom `keychain-access-groups`
/// entry (`$(AppIdentifierPrefix)com.superbrain.ios.shared`). Because it's the
/// *only* custom group listed, the system uses it as the default access group
/// for Keychain items added without an explicit `kSecAttrAccessGroup` — so
/// this code deliberately never hardcodes `$(AppIdentifierPrefix)`'s runtime
/// value (the Team ID, only known after signing), and both targets still land
/// in the same shared keychain.
public final class ServerConfigStore: @unchecked Sendable {
    public static let appGroupSuiteName = "group.com.superbrain.ios.shared"

    private static let serverURLKey = "superbrain.serverURL"
    private static let defaultCollectionKey = "superbrain.defaultShareCollectionID"
    private static let keychainService = "com.superbrain.ios.apiToken"
    private static let keychainAccount = "superbrain-api-token"

    private let defaults: UserDefaults

    public init() {
        self.defaults = UserDefaults(suiteName: Self.appGroupSuiteName) ?? .standard
    }

    public var serverURLString: String? {
        get { defaults.string(forKey: Self.serverURLKey) }
        set { defaults.set(newValue, forKey: Self.serverURLKey) }
    }

    /// The base URL with any trailing slash trimmed, ready to append a path to.
    public var baseURL: URL? {
        guard let raw = serverURLString else { return nil }
        var trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while trimmed.hasSuffix("/") { trimmed.removeLast() }
        guard !trimmed.isEmpty else { return nil }
        return URL(string: trimmed)
    }

    public var apiToken: String? {
        get { readToken() }
        set {
            if let newValue, !newValue.isEmpty {
                writeToken(newValue)
            } else {
                deleteToken()
            }
        }
    }

    public var defaultShareCollectionID: String? {
        get { defaults.string(forKey: Self.defaultCollectionKey) }
        set { defaults.set(newValue, forKey: Self.defaultCollectionKey) }
    }

    public var isConfigured: Bool {
        guard baseURL != nil else { return false }
        guard let token = apiToken, !token.isEmpty else { return false }
        return true
    }

    public func clear() {
        serverURLString = nil
        apiToken = nil
    }

    // MARK: - Keychain

    private func readToken() -> String? {
        var query = Self.keychainQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func writeToken(_ token: String) {
        let data = Data(token.utf8)
        let query = Self.keychainQuery
        let attributes: [String: Any] = [kSecValueData as String: data]

        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updateStatus == errSecItemNotFound {
            var addQuery = query
            addQuery[kSecValueData as String] = data
            SecItemAdd(addQuery as CFDictionary, nil)
        }
    }

    private func deleteToken() {
        SecItemDelete(Self.keychainQuery as CFDictionary)
    }

    private static var keychainQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]
    }
}

/// The backend's access token is exactly 8 alphanumeric characters
/// (`backend/api.py`'s `is_valid_api_token_format`). Mirrors the Android
/// app's `normalizeAccessToken()`: strips anything else and uppercases.
public enum AccessToken {
    public static let length = 8

    public static func normalize(_ raw: String) -> String {
        String(raw.uppercased().filter { $0.isLetter || $0.isNumber })
    }

    public static func isValidFormat(_ token: String) -> Bool {
        token.count == length && token.allSatisfy { $0.isLetter || $0.isNumber }
    }
}
