import Foundation

struct JobsService: Sendable {
    func recentJobs(client: APIClient) async throws -> [Job] {
        try await client.get("/jobs", as: [Job].self)
    }

    func job(path: String, client: APIClient) async throws -> Job {
        try await client.get(path, as: Job.self)
    }
}
