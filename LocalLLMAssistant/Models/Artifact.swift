import Foundation

struct Artifact: Codable, Identifiable, Hashable, Sendable {
    var id: String { name }

    let name: String
    let url: String
}
