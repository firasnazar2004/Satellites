import AppKit
import Foundation
import Observation
import UniformTypeIdentifiers

@MainActor
@Observable
final class FlashcardsViewModel {
    var selectedFileURL: URL?
    var cardsPerChunk = 5
    var maxChunkChars = 3000
    var currentJob: Job?
    var isGenerating = false
    var isDropTargeted = false
    var errorMessage: String?
    var savedArtifactMessage: String?
    var jobStartedAt: Date?
    var elapsedSeconds = 0

    private let flashcardService = FlashcardService()
    private let pollingService = JobPollingService()
    private let notificationService = NotificationService()
    private var pollingTask: Task<Void, Never>?
    private var elapsedTask: Task<Void, Never>?
    private var notifiedTerminalJobIDs = Set<String>()

    isolated deinit {
        pollingTask?.cancel()
        elapsedTask?.cancel()
    }

    init() {
        let savedCards = UserDefaults.standard.integer(forKey: Self.cardsPerChunkKey)
        if (1...12).contains(savedCards) {
            cardsPerChunk = savedCards
        }

        let savedChunkSize = UserDefaults.standard.integer(forKey: Self.maxChunkCharsKey)
        if (500...4000).contains(savedChunkSize) {
            maxChunkChars = savedChunkSize
        }
    }

    var selectedFilename: String {
        selectedFileURL?.lastPathComponent ?? "No file selected"
    }

    var statusText: String {
        currentJob?.status.displayName ?? "Idle"
    }

    var artifacts: [Artifact] {
        currentJob?.artifacts ?? []
    }

    var primaryArtifacts: [Artifact] {
        artifacts.filter { $0.classification == .primaryResult || $0.classification == .secondaryResult }
    }

    var technicalArtifacts: [Artifact] {
        artifacts.filter { $0.classification == .technical }
    }

    var elapsedText: String {
        DateDisplay.duration(TimeInterval(elapsedSeconds))
    }

    func chooseTextFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true

        if panel.runModal() == .OK, let url = panel.url {
            guard url.pathExtension.lowercased() == "txt" else {
                errorMessage = APIError.invalidInputFile.localizedDescription
                return
            }
            selectFile(url)
            errorMessage = nil
        }
    }

    func selectFile(_ url: URL) {
        guard url.pathExtension.lowercased() == "txt" else {
            errorMessage = APIError.invalidInputFile.localizedDescription
            return
        }
        selectedFileURL = url
        errorMessage = nil
        savedArtifactMessage = nil
    }

    func generate(using client: APIClient, onJobUpdate: ((Job) -> Void)? = nil) async {
        pollingTask?.cancel()
        elapsedTask?.cancel()
        currentJob = nil
        errorMessage = nil
        savedArtifactMessage = nil

        guard let selectedFileURL else {
            errorMessage = APIError.invalidInputFile.localizedDescription
            return
        }

        isGenerating = true
        jobStartedAt = Date()
        elapsedSeconds = 0
        startElapsedTimer()
        await notificationService.requestAuthorizationIfNeeded()
        UserDefaults.standard.set(cardsPerChunk, forKey: Self.cardsPerChunkKey)
        UserDefaults.standard.set(maxChunkChars, forKey: Self.maxChunkCharsKey)

        do {
            let submittedJob = try await flashcardService.submit(
                fileURL: selectedFileURL,
                cardsPerChunk: cardsPerChunk,
                maxChunkChars: maxChunkChars,
                client: client
            )
            currentJob = submittedJob
            onJobUpdate?(submittedJob)
            startPolling(job: submittedJob, client: client, onJobUpdate: onJobUpdate)
        } catch {
            isGenerating = false
            elapsedTask?.cancel()
            errorMessage = error.localizedDescription
        }
    }

    func saveArtifact(_ artifact: Artifact, using client: APIClient) async {
        errorMessage = nil
        savedArtifactMessage = nil

        do {
            let data = try await client.downloadArtifact(artifact)
            let panel = NSSavePanel()
            panel.nameFieldStringValue = artifact.name

            guard panel.runModal() == .OK, let destination = panel.url else {
                return
            }

            try data.write(to: destination, options: .atomic)
            savedArtifactMessage = "Saved \(artifact.name)."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startPolling(job: Job, client: APIClient, onJobUpdate: ((Job) -> Void)?) {
        pollingTask = Task {
            do {
                for try await updatedJob in pollingService.poll(initialJob: job, client: client) {
                    currentJob = updatedJob
                    onJobUpdate?(updatedJob)
                    if updatedJob.status.isTerminal {
                        await notifyIfNeeded(updatedJob)
                    }
                    if updatedJob.status == .failed {
                        throw APIError.jobFailure(updatedJob.error)
                    }
                }
            } catch is CancellationError {
                return
            } catch {
                errorMessage = error.localizedDescription
            }

            isGenerating = false
            elapsedTask?.cancel()
        }
    }

    private func startElapsedTimer() {
        elapsedTask = Task {
            while !Task.isCancelled {
                if let jobStartedAt {
                    elapsedSeconds = Int(Date().timeIntervalSince(jobStartedAt))
                }
                try? await Task.sleep(for: .seconds(1))
            }
        }
    }

    private func notifyIfNeeded(_ job: Job) async {
        guard !notifiedTerminalJobIDs.contains(job.id) else {
            return
        }
        notifiedTerminalJobIDs.insert(job.id)
        await notificationService.notifyTerminalFlashcardJob(job)
    }

    private static let cardsPerChunkKey = "flashcards.cardsPerChunk"
    private static let maxChunkCharsKey = "flashcards.maxChunkChars"
}
