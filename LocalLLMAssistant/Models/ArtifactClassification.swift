import Foundation

enum ArtifactClassification: String, Sendable {
    case primaryResult
    case secondaryResult
    case technical
}

extension Artifact {
    var classification: ArtifactClassification {
        let lowercasedName = name.lowercased()
        if lowercasedName == "flashcards.csv" || lowercasedName == "flashcards.json" {
            return .primaryResult
        }
        if lowercasedName == "source.json" {
            return .secondaryResult
        }
        if lowercasedName == "runtime.json" || lowercasedName == "request.json" || lowercasedName == "worker.log" || lowercasedName.hasSuffix(".log") {
            return .technical
        }
        return .secondaryResult
    }
}
