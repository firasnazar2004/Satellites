import Foundation

struct ResearchService: Sendable {
    func submit(
        fileURL: URL,
        maxChunkChars: Int,
        documentType: ResearchDocumentType,
        readingOrder: ResearchReadingOrder,
        client: APIClient
    ) async throws -> Job {
        guard fileURL.pathExtension.lowercased() == "pdf" else {
            throw APIError.validation("Choose a .pdf file for Research.")
        }

        return try await client.uploadResearch(
            fileURL: fileURL,
            maxChunkChars: maxChunkChars,
            documentType: documentType,
            readingOrder: readingOrder
        )
    }
}
