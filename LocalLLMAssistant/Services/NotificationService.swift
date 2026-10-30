import AppKit
import Foundation
import UserNotifications

struct NotificationService: Sendable {
    func requestAuthorizationIfNeeded() async {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .notDetermined else {
            return
        }
        _ = try? await center.requestAuthorization(options: [.alert, .sound])
    }

    func notifyTerminalFlashcardJob(_ job: Job) async {
        guard !NSApp.isActive else {
            return
        }

        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
            return
        }

        let content = UNMutableNotificationContent()
        content.title = "Satellites"
        switch job.status {
        case .completed:
            content.subtitle = "Flashcards complete"
            content.body = "Your flashcards are ready."
        case .failed:
            content.subtitle = "Flashcard generation failed"
            content.body = "Open Satellites for details."
        case .pending, .running:
            return
        }

        let request = UNNotificationRequest(
            identifier: "flashcards-\(job.id)-\(job.status.rawValue)",
            content: content,
            trigger: nil
        )
        try? await UNUserNotificationCenter.current().add(request)
    }
}
