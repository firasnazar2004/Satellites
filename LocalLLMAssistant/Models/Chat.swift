import Foundation

enum ChatRole: String, Codable, Sendable {
    case user
    case assistant
}

struct ChatRequestMessage: Codable, Equatable, Sendable {
    let role: ChatRole
    let content: String
}

struct ChatStreamRequest: Codable, Equatable, Sendable {
    let messages: [ChatRequestMessage]
    let memories: [ChatMemory]?
}

enum ChatStreamEvent: Equatable, Sendable {
    case meta(model: String, assistant: String)
    case memorySave(content: String)
    case token(String)
    case done
    case error(detail: String)
}

struct ChatStreamEventEnvelope: Decodable {
    let type: String
    let model: String?
    let assistant: String?
    let content: String?
    let detail: String?

    var event: ChatStreamEvent? {
        switch type {
        case "meta":
            return .meta(model: model ?? "qwen3:8b", assistant: assistant ?? "Shaka")
        case "memory_save":
            guard let content else {
                return .error(detail: "The server sent a malformed memory save event.")
            }
            return .memorySave(content: content)
        case "token":
            return .token(content ?? "")
        case "done":
            return .done
        case "error":
            return .error(detail: detail ?? "The local model became unavailable.")
        default:
            return nil
        }
    }
}

struct ChatMessage: Identifiable, Equatable {
    let id: UUID
    let role: ChatRole
    var content: String
    var state: ChatMessageState
    let createdAt: Date

    init(
        id: UUID = UUID(),
        role: ChatRole,
        content: String,
        state: ChatMessageState,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.state = state
        self.createdAt = createdAt
    }

    var isValidAPIHistory: Bool {
        switch state {
        case .completed:
            !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .sending, .streaming, .failed, .stopped:
            false
        }
    }
}

enum ChatMessageState: Equatable {
    case sending
    case streaming
    case completed
    case failed(String?)
    case stopped
}

enum ChatValidationError: LocalizedError, Equatable {
    case emptyMessage
    case messageTooLong(maximum: Int)
    case tooManyMessages(maximum: Int)
    case conversationTooLong(maximum: Int)
    case finalMessageMustBeUser

    var errorDescription: String? {
        switch self {
        case .emptyMessage:
            "Enter a message before sending."
        case .messageTooLong(let maximum):
            "One message can be at most \(maximum.formatted()) characters."
        case .tooManyMessages:
            "This conversation has reached the server context limit. Start a new chat to continue."
        case .conversationTooLong:
            "This conversation has reached the server context limit. Start a new chat to continue."
        case .finalMessageMustBeUser:
            "The next chat request must end with your message."
        }
    }
}

enum ChatLimits {
    static let maxMessages = 24
    static let maxMessageCharacters = 8_000
    static let maxTotalCharacters = 32_000

    static func validate(_ messages: [ChatRequestMessage]) throws {
        guard !messages.isEmpty else {
            throw ChatValidationError.emptyMessage
        }
        guard messages.count <= maxMessages else {
            throw ChatValidationError.tooManyMessages(maximum: maxMessages)
        }
        guard messages.last?.role == .user else {
            throw ChatValidationError.finalMessageMustBeUser
        }

        var totalCharacters = 0
        for message in messages {
            let trimmed = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                throw ChatValidationError.emptyMessage
            }
            guard message.content.count <= maxMessageCharacters else {
                throw ChatValidationError.messageTooLong(maximum: maxMessageCharacters)
            }
            totalCharacters += message.content.count
        }

        guard totalCharacters <= maxTotalCharacters else {
            throw ChatValidationError.conversationTooLong(maximum: maxTotalCharacters)
        }
    }
}

struct NDJSONChatStreamParser: Sendable {
    private var buffer = Data()
    private let decoder = JSONDecoder()

    mutating func append(_ byte: UInt8) throws -> [ChatStreamEvent] {
        if byte == 10 {
            return try consumeBufferedLine()
        }

        buffer.append(byte)
        return []
    }

    mutating func finish() throws -> [ChatStreamEvent] {
        guard !buffer.isEmpty else {
            return []
        }
        return try consumeBufferedLine()
    }

    private mutating func consumeBufferedLine() throws -> [ChatStreamEvent] {
        defer { buffer.removeAll(keepingCapacity: true) }

        if buffer.last == 13 {
            buffer.removeLast()
        }

        guard !buffer.isEmpty else {
            return []
        }

        do {
            let envelope = try decoder.decode(ChatStreamEventEnvelope.self, from: buffer)
            if let event = envelope.event {
                return [event]
            }
            return []
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.chatProtocol("The server sent malformed chat stream data.")
        }
    }
}
