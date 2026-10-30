import Foundation

struct MemoryItem: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let content: String
    let createdAt: Date
}

struct ChatMemory: Codable, Equatable, Sendable {
    let id: String
    let content: String
}

enum MemoryLimits {
    static let maxMemories = 100
    static let maxIDCharacters = 128
    static let maxContentCharacters = 500
    static let maxCombinedRequestCharacters = 8_000
}

enum MemoryStoreError: LocalizedError, Equatable {
    case blankContent
    case contentTooLong
    case tooManyMemories
    case invalidID
    case corruptedStore(URL)

    var errorDescription: String? {
        switch self {
        case .blankContent:
            "Memory content cannot be blank."
        case .contentTooLong:
            "A memory can be at most \(MemoryLimits.maxContentCharacters) characters."
        case .tooManyMemories:
            "Shaka can store up to \(MemoryLimits.maxMemories) explicit memories locally."
        case .invalidID:
            "A memory ID must be between 1 and \(MemoryLimits.maxIDCharacters) characters."
        case .corruptedStore(let url):
            "The local memory file could not be read. The original file was preserved at \(url.lastPathComponent)."
        }
    }
}

struct PersistedMemories: Codable, Sendable {
    let version: Int
    var memories: [MemoryItem]
}

final class MemoryStore {
    let storageURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private var cachedMemories: [MemoryItem] = []
    private var hasLoaded = false

    init(storageURL: URL? = nil) {
        self.storageURL = storageURL ?? Self.defaultFileURL()

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder = encoder
    }

    func load() async throws -> [MemoryItem] {
        if hasLoaded {
            return cachedMemories
        }

        guard FileManager.default.fileExists(atPath: storageURL.path) else {
            cachedMemories = []
            hasLoaded = true
            return []
        }

        do {
            let data = try Data(contentsOf: storageURL)
            let document = try decoder.decode(PersistedMemories.self, from: data)
            cachedMemories = document.memories.filter(Self.isLocallyValid(_:))
            hasLoaded = true
            return cachedMemories
        } catch {
            let preservedURL = try preserveCorruptedFile()
            cachedMemories = []
            hasLoaded = true
            throw MemoryStoreError.corruptedStore(preservedURL)
        }
    }

    func allMemories() async throws -> [MemoryItem] {
        try await load()
    }

    func save(content rawContent: String) async throws -> MemoryItem? {
        var memories = try await load()
        let content = rawContent.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !content.isEmpty else {
            throw MemoryStoreError.blankContent
        }
        guard content.count <= MemoryLimits.maxContentCharacters else {
            throw MemoryStoreError.contentTooLong
        }
        guard !memories.contains(where: { $0.content.trimmingCharacters(in: .whitespacesAndNewlines) == content }) else {
            return nil
        }
        guard memories.count < MemoryLimits.maxMemories else {
            throw MemoryStoreError.tooManyMemories
        }

        let item = MemoryItem(id: UUID().uuidString, content: content, createdAt: Date())
        guard Self.isLocallyValid(item) else {
            throw MemoryStoreError.invalidID
        }

        memories.append(item)
        try persist(memories)
        cachedMemories = memories
        hasLoaded = true
        return item
    }

    func delete(id: String) async throws {
        let memories = try await load().filter { $0.id != id }
        try persist(memories)
        cachedMemories = memories
        hasLoaded = true
    }

    func clear() async throws {
        try persist([])
        cachedMemories = []
        hasLoaded = true
    }

    func selectedForRequest() async throws -> [ChatMemory] {
        let memories = try await load()
        var selected: [MemoryItem] = []
        var totalCharacters = 0

        for memory in memories.reversed() {
            guard selected.count < MemoryLimits.maxMemories else {
                break
            }
            let proposedTotal = totalCharacters + memory.content.count
            guard proposedTotal <= MemoryLimits.maxCombinedRequestCharacters else {
                continue
            }
            selected.append(memory)
            totalCharacters = proposedTotal
        }

        return selected.reversed().map { ChatMemory(id: $0.id, content: $0.content) }
    }

    private func persist(_ memories: [MemoryItem]) throws {
        try FileManager.default.createDirectory(at: storageURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let document = PersistedMemories(version: 1, memories: memories)
        let data = try encoder.encode(document)
        try data.write(to: storageURL, options: [.atomic])
    }

    private func preserveCorruptedFile() throws -> URL {
        let timestamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let preservedURL = storageURL.deletingLastPathComponent().appendingPathComponent("memories-corrupt-\(timestamp).json")
        if FileManager.default.fileExists(atPath: storageURL.path) {
            try? FileManager.default.removeItem(at: preservedURL)
            try FileManager.default.copyItem(at: storageURL, to: preservedURL)
        }
        return preservedURL
    }

    private static func isLocallyValid(_ item: MemoryItem) -> Bool {
        let trimmedID = item.id.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedContent = item.content.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmedID.isEmpty
            && trimmedID.count <= MemoryLimits.maxIDCharacters
            && !trimmedContent.isEmpty
            && trimmedContent.count <= MemoryLimits.maxContentCharacters
    }

    private static func defaultFileURL() -> URL {
        let baseURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return baseURL
            .appendingPathComponent("Satellites", isDirectory: true)
            .appendingPathComponent("memories.json")
    }
}
