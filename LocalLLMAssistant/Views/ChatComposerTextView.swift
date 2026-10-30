import AppKit
import SwiftUI

struct ChatComposerTextView: NSViewRepresentable {
    @Binding var text: String
    let focusRequest: Int
    let canSend: () -> Bool
    let onSend: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, canSend: canSend, onSend: onSend)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.drawsBackground = false
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder

        let textView = NSTextView()
        textView.delegate = context.coordinator
        textView.drawsBackground = false
        textView.isRichText = false
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.allowsUndo = true
        textView.font = .systemFont(ofSize: 14)
        textView.textColor = NSColor(AppTheme.textPrimary)
        textView.insertionPointColor = NSColor(AppTheme.textPrimary)
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.textContainer?.lineFragmentPadding = 0
        textView.minSize = NSSize(width: 0, height: 54)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isHorizontallyResizable = false
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]
        textView.string = text

        scrollView.documentView = textView
        context.coordinator.textView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        context.coordinator.canSend = canSend
        context.coordinator.onSend = onSend

        guard let textView = scrollView.documentView as? NSTextView else {
            return
        }

        if textView.string != text {
            textView.string = text
        }

        if context.coordinator.lastFocusRequest != focusRequest {
            context.coordinator.lastFocusRequest = focusRequest
            DispatchQueue.main.async {
                textView.window?.makeFirstResponder(textView)
            }
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        var canSend: () -> Bool
        var onSend: () -> Void
        weak var textView: NSTextView?
        var lastFocusRequest = 0

        init(text: Binding<String>, canSend: @escaping () -> Bool, onSend: @escaping () -> Void) {
            _text = text
            self.canSend = canSend
            self.onSend = onSend
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else {
                return
            }
            text = textView.string
        }

        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            guard commandSelector == #selector(NSResponder.insertNewline(_:)) else {
                return false
            }

            if NSEvent.modifierFlags.contains(.shift) {
                return false
            }

            guard canSend() else {
                return true
            }

            onSend()
            return true
        }
    }
}
