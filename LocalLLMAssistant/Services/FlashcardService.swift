import Foundation

struct FlashcardService: Sendable {
    func submit(fileURL: URL, cardsPerChunk: Int, maxChunkChars: Int, client: APIClient) async throws -> Job {
        guard fileURL.pathExtension.lowercased() == "txt" else {
            throw APIError.invalidInputFile
        }
        return try await client.uploadFlashcards(
            fileURL: fileURL,
            cardsPerChunk: cardsPerChunk,
            maxChunkChars: maxChunkChars
        )
    }
}
