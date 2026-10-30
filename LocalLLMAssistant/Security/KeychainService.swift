import Foundation
import Security

struct KeychainService: Sendable {
    private let service = "com.firasabdelgadir.LocalLLMAssistant"
    private let account = "LocalLLMServerAPIKey"

    func saveAPIKey(_ apiKey: String) throws {
        if apiKey.isEmpty {
            try deleteAPIKey()
            return
        }

        let data = Data(apiKey.utf8)
        let query = baseQuery()
        let attributes: [String: Any] = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        if status == errSecItemNotFound {
            var addQuery = query
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw APIError.keychain(Self.message(for: addStatus))
            }
            return
        }

        guard status == errSecSuccess else {
            throw APIError.keychain(Self.message(for: status))
        }
    }

    func loadAPIKey() throws -> String? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw APIError.keychain(Self.message(for: status))
        }
        guard let data = item as? Data else {
            throw APIError.keychain("Stored API key is not readable.")
        }
        return String(data: data, encoding: .utf8)
    }

    func deleteAPIKey() throws {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw APIError.keychain(Self.message(for: status))
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }

    private static func message(for status: OSStatus) -> String {
        SecCopyErrorMessageString(status, nil) as String? ?? "OSStatus \(status)"
    }
}
