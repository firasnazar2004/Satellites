import Foundation

struct JobPollingService: Sendable {
    func poll(initialJob: Job, client: APIClient) -> AsyncThrowingStream<Job, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var currentJob = initialJob
                continuation.yield(currentJob)

                while !Task.isCancelled && !currentJob.status.isTerminal {
                    try await Task.sleep(for: .seconds(2))
                    currentJob = try await client.get(currentJob.status_url, as: Job.self)
                    continuation.yield(currentJob)
                }

                continuation.finish()
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }
}
