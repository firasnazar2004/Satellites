import Foundation

enum AppSection: String, CaseIterable, Identifiable {
    case chat
    case jobs
    case research
    case flashcards
    case files

    var id: String { rawValue }

    var title: String {
        switch self {
        case .chat:
            "Chat"
        case .jobs:
            "Jobs"
        case .research:
            "Research"
        case .flashcards:
            "Flashcards"
        case .files:
            "Files"
        }
    }

    var systemImage: String {
        switch self {
        case .chat:
            "message"
        case .jobs:
            "list.bullet.rectangle"
        case .research:
            "doc.text.magnifyingglass"
        case .flashcards:
            "rectangle.stack"
        case .files:
            "folder"
        }
    }
}
