import Foundation

struct HealthResponse: Codable, Equatable, Sendable {
    let api: String
    let qwen3_8b_available: Bool
    let Rscript: Bool
    let worker_count: Int
}
