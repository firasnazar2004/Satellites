import Foundation

struct ServerService: Sendable {
    func health(client: APIClient) async throws -> HealthResponse {
        let response = try await client.get("/health", as: HealthResponse.self, timeout: 8)
        guard response.qwen3_8b_available else {
            throw APIError.qwenUnavailable
        }
        return response
    }
}
