import Foundation

struct AppConfiguration: Equatable, Sendable {
    var serverURLString: String
    var apiKey: String

    var serverURL: URL? {
        URL(string: serverURLString.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}

enum ServerConnectionState: Equatable {
    case notConfigured
    case connecting
    case connected(HealthResponse)
    case unreachable
    case authenticationFailed
    case qwenUnavailable
    case failed(String)

    var title: String {
        switch self {
        case .notConfigured:
            "Not configured"
        case .connecting:
            "Connecting"
        case .connected:
            "Connected"
        case .unreachable:
            "Server unreachable"
        case .authenticationFailed:
            "Authentication failed"
        case .qwenUnavailable:
            "Qwen unavailable"
        case .failed:
            "Disconnected"
        }
    }

    var subtitle: String {
        switch self {
        case .notConfigured:
            "Open Settings"
        case .connecting:
            "Checking /health"
        case .connected(let health):
            health.qwen3_8b_available ? "Qwen ready" : "Qwen unavailable"
        case .unreachable:
            "Check Tailscale and FastAPI"
        case .authenticationFailed:
            "Check API key"
        case .qwenUnavailable:
            "Server online"
        case .failed(let message):
            message
        }
    }
}
