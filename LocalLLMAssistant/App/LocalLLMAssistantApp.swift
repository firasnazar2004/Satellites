import SwiftUI

@main
struct LocalLLMAssistantApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 760, minHeight: 620)
                .preferredColorScheme(.dark)
        }
        .windowStyle(.hiddenTitleBar)
    }
}
