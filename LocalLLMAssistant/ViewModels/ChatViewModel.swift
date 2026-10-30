import AppKit
import Foundation
import Observation
import UniformTypeIdentifiers

@MainActor
@Observable
final class ChatViewModel {
    var messages: [ChatMessage] = []
    var draft = ""
    var errorMessage: String?
    var isDropTargeted = false
    var respondingModel = "qwen3:8b"
    var respondingAssistant = "Shaka"
    var landingGreeting: String

    private let chatService = ChatService()
    private let memoryViewModel: MemoryViewModel
    private var greetingProvider = GreetingProvider()
    private var landingGreetingPeriod: DayPeriod
    private var streamingTask: Task<Void, Never>?

    init(memoryViewModel: MemoryViewModel) {
        self.memoryViewModel = memoryViewModel
        let period = DayPeriod.current()
        var provider = GreetingProvider()
        self.landingGreetingPeriod = period
        self.landingGreeting = provider.greeting(for: period)
        self.greetingProvider = provider
    }

    isolated deinit {
        streamingTask?.cancel()
    }

    var isStreaming: Bool {
        streamingTask != nil
    }

    var hasMessages: Bool {
        !messages.isEmpty
    }

    var canSendDraft: Bool {
        !isStreaming && draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }

    var characterLimitText: String? {
        draft.count > 7_200 ? "\(draft.count.formatted()) / \(ChatLimits.maxMessageCharacters.formatted())" : nil
    }

    func sendDraft(using client: APIClient) {
        let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = ChatValidationError.emptyMessage.localizedDescription
            return
        }
        guard !isStreaming else {
            return
        }

        let userMessage = ChatMessage(role: .user, content: trimmed, state: .completed)
        messages.append(userMessage)
        draft = ""
        startAssistantTurn(using: client)
    }

    func retryLastResponse(using client: APIClient) {
        guard !isStreaming else {
            return
        }

        if let last = messages.last, last.role == .assistant {
            switch last.state {
            case .failed, .stopped:
                messages.removeLast()
            case .sending, .streaming, .completed:
                break
            }
        }

        guard messages.last?.role == .user else {
            errorMessage = "Retry is available after a user message fails to receive a completed response."
            return
        }

        startAssistantTurn(using: client)
    }

    func stopStreaming() {
        guard let streamingTask else {
            return
        }
        streamingTask.cancel()
        self.streamingTask = nil
        markActiveAssistantStopped()
    }

    func newChat() {
        streamingTask?.cancel()
        streamingTask = nil
        messages.removeAll()
        draft = ""
        errorMessage = nil
        respondingModel = "qwen3:8b"
        respondingAssistant = "Shaka"
        refreshLandingGreeting(force: true)
    }

    func refreshLandingGreeting(force: Bool = false, date: Date = Date(), calendar: Calendar = .current) {
        let period = DayPeriod.current(for: date, calendar: calendar)
        guard force || period != landingGreetingPeriod else {
            return
        }
        landingGreetingPeriod = period
        landingGreeting = greetingProvider.greeting(for: period)
    }

    func chooseWorkflowFile(route: (URL) -> String?) {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText, .pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true

        if panel.runModal() == .OK, let url = panel.url {
            errorMessage = route(url)
        }
    }

    func handleDroppedWorkflowFile(_ providers: [NSItemProvider], route: @escaping @MainActor (URL) -> String?) -> Bool {
        guard let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            errorMessage = "This file type is not supported yet. Choose a .txt file for Flashcards."
            return false
        }

        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let data = item as? Data {
                url = URL(dataRepresentation: data, relativeTo: nil)
            } else {
                url = item as? URL
            }

            Task { @MainActor in
                guard let url else {
                    self.errorMessage = "This file type is not supported yet. Choose a .txt file for Flashcards."
                    return
                }
                self.errorMessage = route(url)
            }
        }

        return true
    }

    func apiHistoryForNextRequest() -> [ChatRequestMessage] {
        messages.compactMap { message in
            guard message.isValidAPIHistory else {
                return nil
            }
            return ChatRequestMessage(role: message.role, content: message.content)
        }
    }

    private func startAssistantTurn(using client: APIClient) {
        errorMessage = nil
        let history = apiHistoryForNextRequest()

        do {
            try ChatLimits.validate(history)
        } catch {
            errorMessage = error.localizedDescription
            return
        }

        let assistantID = UUID()
        messages.append(
            ChatMessage(
                id: assistantID,
                role: .assistant,
                content: "",
                state: .streaming
            )
        )

        streamingTask = Task { [weak self] in
            guard let self else { return }
            do {
                var completedNormally = false
                let memories = await memoryViewModel.selectedMemoriesForRequest()
                for try await event in chatService.stream(messages: history, memories: memories, client: client) {
                    try Task.checkCancellation()
                    switch event {
                    case .meta(let model, let assistant):
                        respondingModel = model
                        respondingAssistant = assistant
                    case .memorySave(let content):
                        _ = await memoryViewModel.saveMemory(content: content)
                    case .token(let content):
                        appendToken(content, to: assistantID)
                    case .done:
                        completedNormally = true
                        markAssistant(assistantID, state: .completed)
                    case .error(let detail):
                        throw APIError.chatProtocol(detail)
                    }
                }

                if !completedNormally {
                    markAssistant(assistantID, state: .failed("The chat stream ended before completion."))
                    errorMessage = "The chat stream ended before completion."
                }
            } catch is CancellationError {
                markAssistant(assistantID, state: .stopped)
            } catch {
                let message = error.localizedDescription
                markAssistant(assistantID, state: .failed(message))
                errorMessage = message
            }
            streamingTask = nil
        }
    }

    private func appendToken(_ token: String, to id: UUID) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else {
            return
        }
        messages[index].content.append(token)
    }

    private func markAssistant(_ id: UUID, state: ChatMessageState) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else {
            return
        }
        messages[index].state = state
    }

    private func markActiveAssistantStopped() {
        guard let index = messages.lastIndex(where: { $0.role == .assistant && $0.state == .streaming }) else {
            return
        }
        messages[index].state = .stopped
    }
}
