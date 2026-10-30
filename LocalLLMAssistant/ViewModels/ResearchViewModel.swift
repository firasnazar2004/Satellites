import AppKit
import Foundation
import Observation
import UniformTypeIdentifiers

@MainActor
@Observable
final class ResearchViewModel {
    var selectedFileURL: URL?
    var documentType: ResearchDocumentType = .auto
    var readingOrder: ResearchReadingOrder = .auto
    var maxChunkChars = 3000
    var currentJob: Job?
    var isAnalyzing = false
    var isDropTargeted = false
    var errorMessage: String?
    var jobStartedAt: Date?
    var elapsedSeconds = 0

    private let researchService = ResearchService()
    private let pollingService = JobPollingService()
    private var pollingTask: Task<Void, Never>?
    private var elapsedTask: Task<Void, Never>?

    isolated deinit {
        pollingTask?.cancel()
        elapsedTask?.cancel()
    }

    init() {
        let savedChunkSize = UserDefaults.standard.integer(forKey: Self.maxChunkCharsKey)
        if (500...4000).contains(savedChunkSize) {
            maxChunkChars = savedChunkSize
        }

        if let rawDocumentType = UserDefaults.standard.string(forKey: Self.documentTypeKey),
           let savedDocumentType = ResearchDocumentType(rawValue: rawDocumentType) {
            documentType = savedDocumentType
        }

        if let rawReadingOrder = UserDefaults.standard.string(forKey: Self.readingOrderKey),
           let savedReadingOrder = ResearchReadingOrder(rawValue: rawReadingOrder) {
            readingOrder = savedReadingOrder
        }
    }

    var selectedFilename: String {
        selectedFileURL?.lastPathComponent ?? "No PDF selected"
    }

    var statusText: String {
        currentJob?.status.displayName ?? "Idle"
    }

    var elapsedText: String {
        DateDisplay.duration(TimeInterval(elapsedSeconds))
    }

    var researchResult: ResearchResult? {
        currentJob?.research
    }

    var artifacts: [Artifact] {
        currentJob?.artifacts ?? []
    }

    var primaryArtifacts: [Artifact] {
        artifacts.filter { primaryArtifactNames.contains($0.name.lowercased()) }
    }

    var evidenceArtifacts: [Artifact] {
        artifacts.filter { evidenceArtifactNames.contains($0.name.lowercased()) || (!primaryArtifactNames.contains($0.name.lowercased()) && !technicalArtifactNames.contains($0.name.lowercased())) }
    }

    var technicalArtifacts: [Artifact] {
        artifacts.filter { technicalArtifactNames.contains($0.name.lowercased()) }
    }

    var missingModelCommand: String? {
        let combined = [errorMessage, currentJob?.error, currentJob?.research?.processing_error]
            .compactMap { $0 }
            .joined(separator: "\n")
        guard combined.localizedCaseInsensitiveContains("ollama pull qwen3.5:4b") else {
            return nil
        }
        return "ollama pull qwen3.5:4b"
    }

    var hasCompletedJob: Bool {
        currentJob?.status == .completed
    }

    func choosePDF() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true

        if panel.runModal() == .OK, let url = panel.url {
            selectFile(url)
        }
    }

    func selectFile(_ url: URL) {
        guard url.pathExtension.lowercased() == "pdf" else {
            errorMessage = "Choose a .pdf file for Research."
            return
        }
        selectedFileURL = url
        errorMessage = nil
    }

    func analyze(using client: APIClient, onJobUpdate: ((Job) -> Void)? = nil) async {
        pollingTask?.cancel()
        elapsedTask?.cancel()
        currentJob = nil
        errorMessage = nil

        guard let selectedFileURL else {
            errorMessage = "Choose a research PDF before analyzing."
            return
        }

        guard (500...4000).contains(maxChunkChars) else {
            errorMessage = "Maximum chunk size must be between 500 and 4000 characters."
            return
        }

        isAnalyzing = true
        jobStartedAt = Date()
        elapsedSeconds = 0
        startElapsedTimer()
        persistSettings()

        do {
            let submittedJob = try await researchService.submit(
                fileURL: selectedFileURL,
                maxChunkChars: maxChunkChars,
                documentType: documentType,
                readingOrder: readingOrder,
                client: client
            )
            currentJob = submittedJob
            onJobUpdate?(submittedJob)
            startPolling(job: submittedJob, client: client, onJobUpdate: onJobUpdate)
        } catch {
            isAnalyzing = false
            elapsedTask?.cancel()
            errorMessage = error.localizedDescription
        }
    }

    private func startPolling(job: Job, client: APIClient, onJobUpdate: ((Job) -> Void)?) {
        pollingTask = Task {
            do {
                for try await updatedJob in pollingService.poll(initialJob: job, client: client) {
                    currentJob = updatedJob
                    onJobUpdate?(updatedJob)
                    if updatedJob.status == .failed {
                        throw APIError.jobFailure(updatedJob.error)
                    }
                }
            } catch is CancellationError {
                return
            } catch {
                errorMessage = error.localizedDescription
            }

            isAnalyzing = false
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

    private func persistSettings() {
        UserDefaults.standard.set(maxChunkChars, forKey: Self.maxChunkCharsKey)
        UserDefaults.standard.set(documentType.rawValue, forKey: Self.documentTypeKey)
        UserDefaults.standard.set(readingOrder.rawValue, forKey: Self.readingOrderKey)
    }

    private let primaryArtifactNames: Set<String> = [
        "research_report.md",
        "research_limited_overview.md",
        "synthesis.json"
    ]

    private let evidenceArtifactNames: Set<String> = [
        "evidence.json",
        "research_quality.json",
        "pages.json",
        "passages.json"
    ]

    private let technicalArtifactNames: Set<String> = [
        "research_diagnostics.json",
        "research_events.jsonl",
        "rejected_evidence.json"
    ]

    private static let maxChunkCharsKey = "research.maxChunkChars"
    private static let documentTypeKey = "research.documentType"
    private static let readingOrderKey = "research.readingOrder"
}
