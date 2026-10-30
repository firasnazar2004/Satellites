import Foundation

enum APIError: Error, LocalizedError, Equatable {
    case missingServerURL
    case invalidServerURL
    case missingAPIKey
    case insecureHTTPBlocked
    case networkPermissionDenied
    case serverUnreachable
    case authenticationFailed
    case forbidden
    case notFound(String?)
    case uploadTooLarge
    case validation(String?)
    case uploadRejected(String?)
    case invalidResponse
    case decodingFailed(String)
    case qwenUnavailable
    case invalidInputFile
    case jobFailure(String?)
    case artifactDownloadFailure(String?)
    case serverBusy(String?)
    case badGateway(String?)
    case serviceUnavailable(String?)
    case chatProtocol(String)
    case keychain(String)
    case unknownStatus(Int, String?)

    var errorDescription: String? {
        switch self {
        case .missingServerURL:
            "Enter a server URL in Settings."
        case .invalidServerURL:
            "The server URL is not valid."
        case .missingAPIKey:
            "Enter an API key in Settings."
        case .insecureHTTPBlocked:
            "macOS blocked this HTTP request because App Transport Security requires a secure connection. Allow local HTTP loads for development in the app target's Info settings, or use HTTPS."
        case .networkPermissionDenied:
            "macOS blocked the network request because the app sandbox is missing outgoing network permission. Enable Outgoing Connections (Client) for the app target."
        case .serverUnreachable:
            "Unable to reach the Local LLM server. Check that Tailscale is connected, the server computer is online, and FastAPI is running."
        case .authenticationFailed:
            "Authentication failed. Check the API key in Settings."
        case .forbidden:
            "The server refused this remote request. Check that the backend API key is configured and that this client is using it."
        case .notFound(let detail):
            detail ?? "The requested job or artifact was not found."
        case .uploadTooLarge:
            "The selected file is larger than the backend upload limit of 256 MiB."
        case .validation(let detail):
            detail ?? "The request was not accepted by the server."
        case .uploadRejected(let detail):
            detail ?? "The upload was rejected by the server."
        case .invalidResponse:
            "The server returned an invalid response."
        case .decodingFailed:
            "The server response could not be decoded."
        case .qwenUnavailable:
            "The server is online, but qwen3:8b is not currently available."
        case .invalidInputFile:
            "Select a .txt file."
        case .jobFailure(let reason):
            if let reason, !reason.isEmpty {
                "Flashcard generation failed. \(reason)"
            } else {
                "Flashcard generation failed."
            }
        case .artifactDownloadFailure(let detail):
            detail ?? "The artifact could not be downloaded."
        case .serverBusy(let detail):
            detail ?? "Qwen is currently busy processing another task."
        case .badGateway(let detail):
            detail ?? "The AI server returned an invalid response."
        case .serviceUnavailable(let detail):
            detail ?? "Qwen3 8B is currently unavailable on the server."
        case .chatProtocol(let detail):
            detail
        case .keychain(let detail):
            "Keychain error: \(detail)"
        case .unknownStatus(let status, let detail):
            detail ?? "The server returned HTTP \(status)."
        }
    }
}

struct APIErrorDetail: Decodable {
    let detail: Detail

    enum Detail: Decodable {
        case text(String)
        case validation([ValidationIssue])

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let text = try? container.decode(String.self) {
                self = .text(text)
                return
            }
            if let issues = try? container.decode([ValidationIssue].self) {
                self = .validation(issues)
                return
            }
            self = .text("The server returned an error.")
        }

        var safeMessage: String {
            switch self {
            case .text(let text):
                text
            case .validation(let issues):
                issues.map(\.msg).joined(separator: "\n")
            }
        }
    }
}

struct ValidationIssue: Decodable {
    let msg: String
}
