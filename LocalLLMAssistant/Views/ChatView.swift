import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ChatView: View {
    @Bindable var appState: AppState
    @Bindable var viewModel: ChatViewModel
    let serverViewModel: ServerViewModel
    @State private var composerFocusRequest = 0

    var body: some View {
        GeometryReader { proxy in
            let horizontalPadding = proxy.size.width < 620 ? AppTheme.compactContentInset : AppTheme.contentInset

            VStack(spacing: 0) {
                if viewModel.hasMessages {
                    activeChat(horizontalPadding: horizontalPadding)
                } else {
                    emptyChat(horizontalPadding: horizontalPadding)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func emptyChat(horizontalPadding: CGFloat) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeader(
                    title: viewModel.landingGreeting,
                    subtitle: "Ask Qwen anything or choose a workflow."
                )

                composer

                inlineStatus
                workflowShortcuts

                if !appState.jobsViewModel.recentJobs.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: "Recent Jobs")
                        ForEach(appState.jobsViewModel.recentJobs.prefix(3)) { job in
                            Button {
                                appState.selectJob(job)
                            } label: {
                                JobRowView(job: job)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.top, 2)
                }
            }
            .padding(.horizontal, horizontalPadding)
            .padding(.top, 64)
            .padding(.bottom, 40)
            .frame(maxWidth: AppTheme.contentMaxWidth, alignment: .leading)
        }
        .scrollContentBackground(.hidden)
        .onAppear {
            viewModel.refreshLandingGreeting()
        }
    }

    private func activeChat(horizontalPadding: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Chat")
                        .font(.system(size: 27, weight: .medium, design: .rounded))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text("\(viewModel.respondingAssistant) · \(viewModel.respondingModel) · Remote server")
                        .font(.system(size: 13))
                        .foregroundStyle(AppTheme.textSecondary)
                }

                Spacer()

                Button {
                    viewModel.newChat()
                    requestComposerFocus()
                } label: {
                    Label("New Chat", systemImage: "square.and.pencil")
                }
                .buttonStyle(SecondaryLaboratoryButtonStyle())
                .disabled(viewModel.isStreaming)
            }
            .padding(.horizontal, horizontalPadding)
            .padding(.top, 30)
            .padding(.bottom, 18)

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 22) {
                        ForEach(viewModel.messages) { message in
                            ChatMessageRow(message: message, assistantName: viewModel.respondingAssistant)
                                .id(message.id)
                        }
                    }
                    .padding(.horizontal, horizontalPadding)
                    .padding(.bottom, 24)
                    .frame(maxWidth: AppTheme.contentMaxWidth, alignment: .leading)
                }
                .scrollContentBackground(.hidden)
                .onChange(of: viewModel.messages.count) { _, _ in
                    scrollToNewest(with: proxy)
                }
                .onChange(of: viewModel.messages.last?.content ?? "") { _, _ in
                    scrollToNewest(with: proxy)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                inlineStatus
                composer
            }
            .padding(.horizontal, horizontalPadding)
            .padding(.bottom, 24)
            .frame(maxWidth: AppTheme.contentMaxWidth, alignment: .leading)
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                ChatComposerTextView(
                    text: $viewModel.draft,
                    focusRequest: composerFocusRequest,
                    canSend: { !sendDisabled },
                    onSend: send
                )
                .frame(minHeight: 54, maxHeight: 92)
                .padding(.horizontal, 13)
                .padding(.top, 12)

                if viewModel.draft.isEmpty {
                    Text("Send a message...")
                        .font(.system(size: 14))
                        .foregroundStyle(AppTheme.textSecondary)
                        .padding(.horizontal, 18)
                        .padding(.top, 17)
                        .allowsHitTesting(false)
                }
            }

            HStack(spacing: 10) {
                Button {
                    viewModel.chooseWorkflowFile { url in
                        appState.routeSelectedFile(url)
                    }
                } label: {
                    Image(systemName: "paperclip")
                        .font(.system(size: 16, weight: .medium))
                        .frame(width: 30, height: 30)
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textSecondary)
                .accessibilityLabel("Choose workflow file")

                if let characterLimitText = viewModel.characterLimitText {
                    Text(characterLimitText)
                        .font(.system(size: 11.5).monospacedDigit())
                        .foregroundStyle(viewModel.draft.count > ChatLimits.maxMessageCharacters ? AppTheme.failure : AppTheme.textTertiary)
                }

                Spacer()

                modelChip

                if viewModel.isStreaming {
                    Button {
                        viewModel.stopStreaming()
                    } label: {
                        Image(systemName: "stop.fill")
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textPrimary)
                    .laboratorySurface(fill: AppTheme.failure.opacity(0.72), topFill: AppTheme.failure.opacity(0.82), radius: 8, border: Color.white.opacity(0.08))
                    .accessibilityLabel("Stop generation")
                } else {
                    Button {
                        send()
                    } label: {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 15, weight: .semibold))
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textPrimary)
                    .background(
                        LinearGradient(
                            colors: [sendDisabled ? AppTheme.elevatedSurfaceTop : AppTheme.accentHover.opacity(0.84), sendDisabled ? AppTheme.elevatedSurface : AppTheme.accent],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.white.opacity(sendDisabled ? 0.05 : 0.075), lineWidth: 1)
                    )
                    .disabled(sendDisabled)
                    .keyboardShortcut(.return, modifiers: [.command])
                    .accessibilityLabel("Send message")
                }
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, minHeight: 122)
        .glassSurface(
            fill: viewModel.isDropTargeted ? AppTheme.inputSurface.opacity(0.9) : AppTheme.inputSurface.opacity(0.78),
            topFill: AppTheme.inputSurfaceTop.opacity(0.84),
            material: .thinMaterial,
            radius: AppTheme.composerRadius,
            border: viewModel.isDropTargeted ? AppTheme.accent.opacity(0.55) : AppTheme.borderStrong
        )
        .onDrop(of: [.fileURL], isTargeted: $viewModel.isDropTargeted) { providers in
            viewModel.handleDroppedWorkflowFile(providers) { url in
                appState.routeSelectedFile(url)
            }
        }
    }

    private var modelChip: some View {
        HStack(spacing: 6) {
            Image(systemName: "server.rack")
                .font(.system(size: 12, weight: .medium))
            Text(viewModel.respondingModel)
                .font(.system(size: 13, weight: .semibold))
        }
        .foregroundStyle(AppTheme.textPrimary)
        .padding(.horizontal, 10)
        .frame(height: 34)
        .glassSurface(fill: AppTheme.mainBackground.opacity(0.72), topFill: AppTheme.mainBackgroundTop.opacity(0.82), material: .thinMaterial, radius: 8, border: AppTheme.borderSubtle)
    }

    @ViewBuilder
    private var inlineStatus: some View {
        if let errorMessage = viewModel.errorMessage {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(errorMessage)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.failure)
                    .fixedSize(horizontal: false, vertical: true)

                if canRetry {
                    Button("Retry") {
                        retry()
                    }
                    .buttonStyle(SecondaryLaboratoryButtonStyle())
                }

                if isConversationLimitMessage(errorMessage) {
                    Button("New Chat") {
                        viewModel.newChat()
                        requestComposerFocus()
                    }
                    .buttonStyle(SecondaryLaboratoryButtonStyle())
                }
            }
        }
    }

    private var workflowShortcuts: some View {
        HStack(spacing: 16) {
            workflowButton(
                title: "Research",
                subtitle: "PDF papers",
                systemImage: "doc.text.magnifyingglass",
                isEnabled: true
            ) {
                appState.selectedSection = .research
            }

            workflowButton(
                title: "Flashcards",
                subtitle: "Notes to cards",
                systemImage: "rectangle.stack",
                isEnabled: true
            ) {
                appState.selectedSection = .flashcards
            }
        }
    }

    private func workflowButton(title: String, subtitle: String, systemImage: String, isEnabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: systemImage)
                    .font(.system(size: 21, weight: .medium))
                    .foregroundStyle(isEnabled ? AppTheme.textPrimary : AppTheme.textTertiary)
                    .frame(width: 26)

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textSecondary)
                }

                Spacer()
            }
            .padding(.horizontal, 18)
            .frame(height: 72)
            .glassSurface(
                fill: AppTheme.elevatedSurface.opacity(isEnabled ? 0.72 : 0.46),
                topFill: AppTheme.elevatedSurfaceTop.opacity(isEnabled ? 0.82 : 0.52),
                material: .thinMaterial,
                radius: 8,
                border: AppTheme.borderSubtle
            )
            .opacity(isEnabled ? 1 : 0.78)
        }
        .buttonStyle(.plain)
    }

    private var sendDisabled: Bool {
        guard case .connected(let health) = serverViewModel.connectionState, health.qwen3_8b_available else {
            return true
        }
        return !viewModel.canSendDraft || viewModel.draft.count > ChatLimits.maxMessageCharacters
    }

    private var canRetry: Bool {
        guard let last = viewModel.messages.last, last.role == .assistant else {
            return false
        }
        switch last.state {
        case .failed, .stopped:
            return true
        case .sending, .streaming, .completed:
            return false
        }
    }

    private func send() {
        guard !sendDisabled else {
            return
        }
        do {
            viewModel.sendDraft(using: try serverViewModel.makeClient())
            requestComposerFocus()
        } catch {
            viewModel.errorMessage = error.localizedDescription
        }
    }

    private func requestComposerFocus() {
        composerFocusRequest += 1
    }

    private func retry() {
        do {
            viewModel.retryLastResponse(using: try serverViewModel.makeClient())
        } catch {
            viewModel.errorMessage = error.localizedDescription
        }
    }

    private func scrollToNewest(with proxy: ScrollViewProxy) {
        guard let id = viewModel.messages.last?.id else {
            return
        }
        withAnimation(.easeInOut(duration: 0.16)) {
            proxy.scrollTo(id, anchor: .bottom)
        }
    }

    private func isConversationLimitMessage(_ message: String) -> Bool {
        message.localizedCaseInsensitiveContains("context limit") || message.localizedCaseInsensitiveContains("at most")
    }
}

private struct ChatMessageRow: View {
    let message: ChatMessage
    let assistantName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Text(message.role == .user ? "You" : assistantName)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(message.role == .user ? AppTheme.textSecondary : AppTheme.accentHover)

                if message.role == .assistant && message.state == .streaming && message.content.isEmpty {
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.62)
                }

                if message.role == .assistant, let statusText {
                    Text(statusText)
                        .font(.system(size: 11.5))
                        .foregroundStyle(statusColor)
                }
            }

            Text(contentText)
                .font(.system(size: 14))
                .lineSpacing(3)
                .foregroundStyle(AppTheme.textPrimary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .contextMenu {
                    Button("Copy") {
                        copy(contentText)
                    }
                }
        }
        .padding(message.role == .user ? 13 : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            if message.role == .user {
                RoundedRectangle(cornerRadius: 9)
                    .fill(AppTheme.elevatedSurface.opacity(0.52))
                    .overlay(
                        RoundedRectangle(cornerRadius: 9)
                            .stroke(AppTheme.borderSubtle, lineWidth: 1)
                    )
            }
        }
    }

    private var contentText: String {
        if message.role == .assistant && message.state == .streaming && message.content.isEmpty {
            return "Thinking..."
        }
        return message.content
    }

    private var statusText: String? {
        switch message.state {
        case .failed:
            "Incomplete"
        case .stopped:
            "Stopped"
        case .sending, .streaming, .completed:
            nil
        }
    }

    private var statusColor: Color {
        switch message.state {
        case .failed:
            AppTheme.failure
        case .stopped:
            AppTheme.warning
        case .sending, .streaming, .completed:
            AppTheme.textSecondary
        }
    }

    private func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
