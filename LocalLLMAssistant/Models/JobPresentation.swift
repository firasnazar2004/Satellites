import Foundation

extension Job {
    var shortID: String {
        String(id.prefix(8))
    }

    var displayLabel: String {
        "\(pipeline.displayName) \(shortID)"
    }

    var bestActivityDate: Date {
        finished_at ?? started_at ?? created_at
    }

    var elapsedInterval: TimeInterval? {
        let start = started_at ?? created_at
        let end = finished_at ?? Date()
        return max(0, end.timeIntervalSince(start))
    }
}

extension Pipeline {
    var displayName: String {
        switch self {
        case .flashcards:
            "Flashcards"
        case .dataset:
            "Dataset"
        case .research:
            "Research"
        }
    }
}

enum DateDisplay {
    static let relativeFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter
    }()

    static let absoluteFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    static func relative(_ date: Date) -> String {
        relativeFormatter.localizedString(for: date, relativeTo: Date())
    }

    static func duration(_ interval: TimeInterval?) -> String {
        guard let interval else {
            return "Not started"
        }
        let seconds = Int(interval.rounded())
        let minutes = seconds / 60
        let remainingSeconds = seconds % 60
        if minutes >= 60 {
            let hours = minutes / 60
            let remainingMinutes = minutes % 60
            return "\(hours)h \(remainingMinutes)m"
        }
        if minutes > 0 {
            return "\(minutes)m \(remainingSeconds)s"
        }
        return "\(remainingSeconds)s"
    }
}
