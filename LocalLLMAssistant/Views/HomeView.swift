import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct HomeView: View {
    @Bindable var appState: AppState
    @State private var isDropTargeted = false
    @State private var message: String?

    var body: some View {
        GeometryReader { proxy in
            let horizontalPadding = proxy.size.width < 620 ? AppTheme.compactContentInset : AppTheme.contentInset

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    PageHeader(
                        title: "What do you want to do today?",
                        subtitle: "Upload a file or choose a workflow."
                    )

                    composer

                    if let message {
                        Text(message)
                            .font(.system(size: 13))
                            .foregroundStyle(AppTheme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

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
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Drop a file or choose a workflow...")
                .font(.system(size: 14))
                .foregroundStyle(AppTheme.textSecondary)
                .padding(.top, 16)
                .padding(.horizontal, 18)

            Spacer()

            HStack {
                Button {
                    chooseFile()
                } label: {
                    Image(systemName: "paperclip")
                        .font(.system(size: 16, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textSecondary)
                .accessibilityLabel("Choose File")

                Spacer()

                Text("qwen3:8b")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                    .padding(.horizontal, 12)
                    .frame(height: 34)
                    .laboratorySurface(fill: AppTheme.mainBackground, topFill: AppTheme.mainBackgroundTop, radius: 8, border: AppTheme.borderSubtle)

                Button {
                    appState.selectedSection = .flashcards
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 15, weight: .semibold))
                        .frame(width: 34, height: 34)
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textPrimary)
                .background(
                    LinearGradient(
                        colors: [AppTheme.accentHover.opacity(0.84), AppTheme.accent],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(alignment: .top) {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                }
                .accessibilityLabel("Open Flashcards")
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, minHeight: 104, maxHeight: 104)
        .laboratorySurface(
            fill: isDropTargeted ? AppTheme.inputSurface.opacity(0.95) : AppTheme.inputSurface,
            topFill: AppTheme.inputSurfaceTop,
            radius: AppTheme.composerRadius,
            border: isDropTargeted ? AppTheme.accent.opacity(0.55) : AppTheme.borderStrong
        )
        .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers)
        }
        .accessibilityLabel("Drop a file or choose one")
    }

    private var workflowShortcuts: some View {
        HStack(spacing: 16) {
            workflowButton(
                title: "Research",
                subtitle: "PDF papers · Coming later",
                systemImage: "doc.text",
                isEnabled: false
            ) {
                message = "Research workflow is not enabled in this client yet."
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
            .laboratorySurface(
                fill: AppTheme.elevatedSurface.opacity(isEnabled ? 0.78 : 0.52),
                topFill: AppTheme.elevatedSurfaceTop.opacity(isEnabled ? 0.78 : 0.52),
                radius: 8,
                border: AppTheme.borderSubtle
            )
            .opacity(isEnabled ? 1 : 0.78)
        }
        .buttonStyle(.plain)
    }

    private func chooseFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText, .pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true

        if panel.runModal() == .OK, let url = panel.url {
            message = appState.routeSelectedFile(url)
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            message = "This file type is not supported yet. Choose a .txt file for Flashcards."
            return false
        }

        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let data = item as? Data {
                url = URL(dataRepresentation: data, relativeTo: nil)
            } else {
                url = item as? URL
            }

            Task { @MainActor in
                guard let url else {
                    message = "This file type is not supported yet. Choose a .txt file for Flashcards."
                    return
                }
                message = appState.routeSelectedFile(url)
            }
        }

        return true
    }
}
