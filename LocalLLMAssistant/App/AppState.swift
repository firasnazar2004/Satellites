import Foundation
import Observation

@MainActor
@Observable
final class AppState {
    var selectedSection: AppSection {
        didSet {
            UserDefaults.standard.set(selectedSection.rawValue, forKey: Self.selectedSectionKey)
        }
    }

    var selectedJobID: String?

    let serverViewModel: ServerViewModel
    let flashcardsViewModel: FlashcardsViewModel
    let researchViewModel: ResearchViewModel
    let jobsViewModel: JobsViewModel
    let chatViewModel: ChatViewModel
    let memoryViewModel: MemoryViewModel

    init() {
        self.serverViewModel = ServerViewModel()
        self.flashcardsViewModel = FlashcardsViewModel()
        self.researchViewModel = ResearchViewModel()
        self.jobsViewModel = JobsViewModel()
        self.memoryViewModel = MemoryViewModel(store: MemoryStore())
        self.chatViewModel = ChatViewModel(memoryViewModel: memoryViewModel)

        let savedSection = UserDefaults.standard.string(forKey: Self.selectedSectionKey)
        self.selectedSection = savedSection.flatMap(AppSection.init(rawValue:)) ?? .chat
    }

    func selectJob(_ job: Job) {
        selectedJobID = job.id
        jobsViewModel.selectedJobID = job.id
        selectedSection = .jobs
    }

    func routeSelectedFile(_ url: URL) -> String? {
        switch url.pathExtension.lowercased() {
        case "txt":
            flashcardsViewModel.selectFile(url)
            selectedSection = .flashcards
            return nil
        case "pdf":
            researchViewModel.selectFile(url)
            selectedSection = .research
            return nil
        default:
            return "This file type is not supported yet. Choose a .txt file for Flashcards."
        }
    }

    private static let selectedSectionKey = "selectedSection"
}
