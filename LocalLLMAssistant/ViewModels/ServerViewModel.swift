import Foundation
import Observation

@MainActor
@Observable
final class ServerViewModel {
    var serverURLString: String {
        didSet {
            UserDefaults.standard.set(serverURLString, forKey: Self.serverURLKey)
        }
    }

    var apiKey: String = ""
    var connectionState: ServerConnectionState = .notConfigured
    var errorMessage: String?
    var showingSettings = false

    private let keychain = KeychainService()
    private let serverService = ServerService()
    private var lastHealthCheck: Date?

    init() {
        serverURLString = UserDefaults.standard.string(forKey: Self.serverURLKey) ?? ""
        do {
            apiKey = try keychain.loadAPIKey() ?? ""
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var configuration: AppConfiguration {
        AppConfiguration(serverURLString: serverURLString, apiKey: apiKey)
    }

    func save() {
        do {
            UserDefaults.standard.set(serverURLString.trimmingCharacters(in: .whitespacesAndNewlines), forKey: Self.serverURLKey)
            try keychain.saveAPIKey(apiKey.trimmingCharacters(in: .whitespacesAndNewlines))
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func makeClient() throws -> APIClient {
        let trimmedURL = serverURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedURL.isEmpty else {
            throw APIError.missingServerURL
        }
        guard let url = URL(string: trimmedURL), url.scheme != nil, url.host != nil else {
            throw APIError.invalidServerURL
        }
        guard !trimmedKey.isEmpty else {
            throw APIError.missingAPIKey
        }
        return APIClient(baseURL: url, apiKey: trimmedKey)
    }

    func testConnection() async {
        await refreshConnection(saveFirst: true)
    }

    func refreshConnectionIfConfigured() async {
        guard !serverURLString.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            connectionState = .notConfigured
            return
        }
        await refreshConnection(saveFirst: false)
    }

    func refreshConnectionIfStale() async {
        if let lastHealthCheck, Date().timeIntervalSince(lastHealthCheck) < 30 {
            return
        }
        await refreshConnectionIfConfigured()
    }

    private func refreshConnection(saveFirst: Bool) async {
        connectionState = .connecting
        errorMessage = nil

        do {
            if saveFirst {
                save()
            }
            let response = try await serverService.health(client: makeClient())
            connectionState = .connected(response)
            lastHealthCheck = Date()
        } catch APIError.qwenUnavailable {
            connectionState = .qwenUnavailable
            errorMessage = APIError.qwenUnavailable.localizedDescription
            lastHealthCheck = Date()
        } catch APIError.authenticationFailed {
            connectionState = .authenticationFailed
            errorMessage = APIError.authenticationFailed.localizedDescription
        } catch APIError.serverUnreachable {
            connectionState = .unreachable
            errorMessage = APIError.serverUnreachable.localizedDescription
        } catch {
            connectionState = .failed(error.localizedDescription)
            errorMessage = error.localizedDescription
        }
    }

    private static let serverURLKey = "serverURL"
}
