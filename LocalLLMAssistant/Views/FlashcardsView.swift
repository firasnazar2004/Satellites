import SwiftUI
import UniformTypeIdentifiers

struct FlashcardsView: View {
    let serverViewModel: ServerViewModel
    @Bindable var jobsViewModel: JobsViewModel
    @Bindable var viewModel: FlashcardsViewModel

    var body: some View {
        GeometryReader { proxy in
            let horizontalPadding = proxy.size.width < 620 ? AppTheme.compactContentInset : AppTheme.contentInset

            ScrollView {
                VStack(alignment: .leading, spacing: 25) {
                    PageHeader(
                        title: "Flashcards",
                        subtitle: "Turn study notes into structured flashcards."
                    )
                    fileDropZone
                    settingsSection
                    actionSection

                    if viewModel.currentJob != nil || viewModel.isGenerating {
                        ActiveFlashcardJobView(viewModel: viewModel)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(AppTheme.failure)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    if let savedArtifactMessage = viewModel.savedArtifactMessage {
                        Text(savedArtifactMessage)
                            .font(.callout)
                            .foregroundStyle(AppTheme.success)
                    }

                    ArtifactListView(
                        title: "Results",
                        artifacts: viewModel.primaryArtifacts,
                        technicalArtifacts: viewModel.technicalArtifacts,
                        serverViewModel: serverViewModel
                    )
                }
                .padding(.horizontal, horizontalPadding)
                .padding(.vertical, 38)
                .frame(minWidth: AppTheme.contentMinWidth, maxWidth: AppTheme.contentMaxWidth, alignment: .leading)
            }
            .scrollContentBackground(.hidden)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var fileDropZone: some View {
        VStack(spacing: 10) {
            Image(systemName: "doc.text")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(AppTheme.textSecondary)

            VStack(spacing: 4) {
                Text("Drop a .txt file here")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                Text(viewModel.selectedFileURL == nil ? "or choose a file from this Mac" : viewModel.selectedFilename)
                    .font(.system(size: 12, weight: viewModel.selectedFileURL == nil ? .regular : .medium))
                    .foregroundStyle(viewModel.selectedFileURL == nil ? AppTheme.textSecondary : AppTheme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Button {
                viewModel.chooseTextFile()
            } label: {
                Label("Choose File", systemImage: "plus")
            }
            .buttonStyle(SecondaryLaboratoryButtonStyle())
        }
        .frame(maxWidth: .infinity, minHeight: 174)
        .padding(18)
        .laboratorySurface(
            fill: AppTheme.dropSurfaceBottom,
            topFill: AppTheme.dropSurfaceTop,
            radius: AppTheme.composerRadius,
            border: viewModel.isDropTargeted ? AppTheme.accent.opacity(0.55) : AppTheme.borderStrong
        )
        .onDrop(of: [.fileURL], isTargeted: $viewModel.isDropTargeted) { providers in
            handleDrop(providers)
        }
        .accessibilityLabel("Drop a text file for flashcard generation")
    }

    private var settingsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle(title: "Settings")

            Grid(alignment: .leading, horizontalSpacing: 30, verticalSpacing: 10) {
                GridRow {
                    Text("Cards per chunk")
                        .font(.system(size: 13))
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(width: 190, alignment: .leading)
                    Stepper(value: $viewModel.cardsPerChunk, in: 1...12) {
                        Text("\(viewModel.cardsPerChunk)")
                            .frame(width: 42, alignment: .trailing)
                            .monospacedDigit()
                            .foregroundStyle(AppTheme.textPrimary)
                    }
                    .padding(.horizontal, 8)
                    .frame(width: 92, height: 30)
                    .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 6, border: AppTheme.borderSubtle)
                }

                GridRow {
                    Text("Maximum chunk size")
                        .font(.system(size: 13))
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(width: 190, alignment: .leading)
                    Stepper(value: $viewModel.maxChunkChars, in: 500...4000, step: 100) {
                        Text("\(viewModel.maxChunkChars)")
                            .frame(width: 42, alignment: .trailing)
                            .monospacedDigit()
                            .foregroundStyle(AppTheme.textPrimary)
                    }
                    .padding(.horizontal, 8)
                    .frame(width: 92, height: 30)
                    .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 6, border: AppTheme.borderSubtle)
                }
            }
        }
    }

    private var actionSection: some View {
        HStack {
            Spacer()
            Button {
                Task {
                    do {
                        try await viewModel.generate(using: serverViewModel.makeClient()) { job in
                            jobsViewModel.upsert(job)
                            if job.status.isTerminal, let client = try? serverViewModel.makeClient() {
                                Task {
                                    await jobsViewModel.refresh(using: client)
                                }
                            }
                        }
                    } catch {
                        viewModel.errorMessage = error.localizedDescription
                    }
                }
            } label: {
                Label("Generate Flashcards", systemImage: "rectangle.stack.badge.plus")
            }
            .buttonStyle(PrimaryLaboratoryButtonStyle())
            .disabled(viewModel.isGenerating)
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            viewModel.errorMessage = APIError.invalidInputFile.localizedDescription
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
                    viewModel.errorMessage = APIError.invalidInputFile.localizedDescription
                    return
                }
                viewModel.selectFile(url)
            }
        }

        return true
    }
}

private struct ActiveFlashcardJobView: View {
    @Bindable var viewModel: FlashcardsViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Generating Flashcards")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text(viewModel.selectedFilename)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textSecondary)
                }
                Spacer()
                Text("Elapsed \(viewModel.elapsedText)")
                    .font(.system(size: 12).monospacedDigit())
                    .foregroundStyle(AppTheme.textSecondary)
            }

            VStack(alignment: .leading, spacing: 8) {
                stageRow("Submitted", isComplete: viewModel.currentJob != nil, isActive: false)
                stageRow("Queued", isComplete: isPastQueued, isActive: viewModel.currentJob?.status == .pending)
                stageRow("Processing", isComplete: isComplete, isActive: viewModel.currentJob?.status == .running)
                stageRow(terminalTitle, isComplete: isComplete, isActive: viewModel.currentJob?.status == .failed)
            }

            if viewModel.isGenerating {
                ProgressView()
                    .progressViewStyle(.linear)
            }
        }
        .padding(16)
        .laboratorySurface(fill: AppTheme.elevatedSurface.opacity(0.7), radius: 8, border: AppTheme.borderSubtle)
    }

    private var isPastQueued: Bool {
        guard let status = viewModel.currentJob?.status else {
            return false
        }
        return status == .running || status == .completed || status == .failed
    }

    private var isComplete: Bool {
        viewModel.currentJob?.status == .completed
    }

    private var terminalTitle: String {
        viewModel.currentJob?.status == .failed ? "Failed" : "Complete"
    }

    private func stageRow(_ title: String, isComplete: Bool, isActive: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: symbol(isComplete: isComplete, isActive: isActive))
                .foregroundStyle(color(isComplete: isComplete, isActive: isActive))
            Text(title)
                .foregroundStyle(AppTheme.textPrimary)
            if isActive {
                Text(viewModel.statusText)
                    .foregroundStyle(AppTheme.textSecondary)
            }
        }
        .font(.system(size: 13))
    }

    private func symbol(isComplete: Bool, isActive: Bool) -> String {
        if isComplete {
            return "checkmark.circle.fill"
        }
        if viewModel.currentJob?.status == .failed && isActive {
            return "xmark.circle.fill"
        }
        return isActive ? "smallcircle.filled.circle" : "circle"
    }

    private func color(isComplete: Bool, isActive: Bool) -> Color {
        if isComplete {
            return AppTheme.success
        }
        if viewModel.currentJob?.status == .failed && isActive {
            return AppTheme.failure
        }
        return isActive ? AppTheme.progress : AppTheme.textTertiary
    }
}
