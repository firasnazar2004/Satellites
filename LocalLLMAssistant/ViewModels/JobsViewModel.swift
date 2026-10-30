import Foundation
import Observation

enum JobFilter: String, CaseIterable, Identifiable {
    case all
    case processing
    case completed
    case failed

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all:
            "All"
        case .processing:
            "Processing"
        case .completed:
            "Completed"
        case .failed:
            "Failed"
        }
    }
}

@MainActor
@Observable
final class JobsViewModel {
    var jobs: [Job] = []
    var selectedJobID: String?
    var filter: JobFilter = .all
    var searchText = ""
    var isRefreshing = false
    var errorMessage: String?

    private let jobsService = JobsService()

    var filteredJobs: [Job] {
        filtered(jobs)
    }

    var recentJobs: [Job] {
        Array(filtered(jobs).prefix(5))
    }

    var selectedJob: Job? {
        guard let selectedJobID else {
            return filteredJobs.first
        }
        return jobs.first { $0.id == selectedJobID }
    }

    func filtered(_ source: [Job]) -> [Job] {
        let search = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return source.filter { job in
            switch filter {
            case .all:
                break
            case .processing:
                guard job.status == .pending || job.status == .running else { return false }
            case .completed:
                guard job.status == .completed else { return false }
            case .failed:
                guard job.status == .failed else { return false }
            }

            guard !search.isEmpty else { return true }
            return job.displayLabel.lowercased().contains(search)
                || job.pipeline.displayName.lowercased().contains(search)
                || job.shortID.lowercased().contains(search)
                || job.status.displayName.lowercased().contains(search)
    }
    }

    func refresh(using client: APIClient) async {
        isRefreshing = true
        errorMessage = nil
        do {
            jobs = try await jobsService.recentJobs(client: client)
            if selectedJobID == nil {
                selectedJobID = jobs.first?.id
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isRefreshing = false
    }

    func upsert(_ job: Job) {
        if let index = jobs.firstIndex(where: { $0.id == job.id }) {
            jobs[index] = job
        } else {
            jobs.insert(job, at: 0)
        }
    }
}
