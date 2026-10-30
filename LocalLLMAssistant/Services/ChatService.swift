import Foundation

struct ChatService: Sendable {
    func stream(messages: [ChatRequestMessage], memories: [ChatMemory], client: APIClient) -> AsyncThrowingStream<ChatStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try ChatLimits.validate(messages)
                    let request = ChatStreamRequest(messages: messages, memories: memories.isEmpty ? nil : memories)
                    let bytes = try await client.streamChat(request)
                    var parser = NDJSONChatStreamParser()

                    for try await byte in bytes {
                        try Task.checkCancellation()
                        for event in try parser.append(byte) {
                            continuation.yield(event)
                        }
                    }

                    for event in try parser.finish() {
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish(throwing: CancellationError())
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }
}
