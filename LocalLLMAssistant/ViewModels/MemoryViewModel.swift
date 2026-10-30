import Foundation
import Observation

@MainActor
@Observable
final class MemoryViewModel {
    var memories: [MemoryItem] = []
    var errorMessage: String?
    var savedMessage: String?
    var isLoading = false

    let store: MemoryStore

    init(store: MemoryStore) {
        self.store = store
    }

    var storagePath: String {
        store.storageURL.path
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }

        do {
            memories = try await store.load()
            errorMessage = nil
        } catch {
            memories = []
            errorMessage = error.localizedDescription
        }
    }

    func saveMemory(content: String) async -> MemoryItem? {
        do {
            let item = try await store.save(content: content)
            memories = try await store.allMemories()
            if item != nil {
                savedMessage = "Shaka saved a memory."
            }
            return item
        } catch {
            errorMessage = "Shaka couldn't save this memory locally."
            return nil
        }
    }

    func selectedMemoriesForRequest() async -> [ChatMemory] {
        do {
            return try await store.selectedForRequest()
        } catch {
            errorMessage = error.localizedDescription
            return []
        }
    }

    func delete(_ memory: MemoryItem) async {
        do {
            try await store.delete(id: memory.id)
            memories = try await store.allMemories()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearAll() async {
        do {
            try await store.clear()
            memories = []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
