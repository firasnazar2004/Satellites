import Foundation

struct Job: Codable, Identifiable, Sendable {
    let id: String
    let pipeline: Pipeline
    let status: JobStatus
    let created_at: Date
    let started_at: Date?
    let finished_at: Date?
    let error: String?
    let artifacts: [Artifact]
    let status_url: String
    let research: ResearchResult?
}

enum JobStatus: String, Codable, Sendable {
    case pending
    case running
    case completed
    case failed

    var displayName: String {
        switch self {
        case .pending:
            "Queued"
        case .running:
            "Processing"
        case .completed:
            "Completed"
        case .failed:
            "Failed"
        }
    }

    var isTerminal: Bool {
        self == .completed || self == .failed
    }
}

enum Pipeline: String, Codable, Sendable {
    case flashcards
    case dataset
    case research
}

