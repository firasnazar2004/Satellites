import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ResearchView: View {
    let serverViewModel: ServerViewModel
    @Bindable var jobsViewModel: JobsViewModel
    @Bindable var viewModel: ResearchViewModel

    var body: some View {
        GeometryReader { proxy in
            let horizontalPadding = proxy.size.width < 620 ? AppTheme.compactContentInset : AppTheme.contentInset

            ScrollView {
                VStack(alignment: .leading, spacing: 25) {
                    VStack(alignment: .leading, spacing: 12) {
                        PageHeader(
                            title: "Research",
                            subtitle: "Extract evidence and synthesize research from PDF papers."
                        )
                        researchModelChip
                    }

                    pdfDropZone
                    settingsSection
                    actionSection

                    if viewModel.currentJob != nil || viewModel.isAnalyzing {
                        ActiveResearchJobView(viewModel: viewModel)
                    }

                    if let command = viewModel.missingModelCommand {
                        MissingResearchModelView(command: command)
                    }

                    if let errorMessage = viewModel.errorMessage, viewModel.missingModelCommand == nil {
                        Text(errorMessage)
                            .font(.callout)
                            .foregroundStyle(AppTheme.failure)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    if let job = viewModel.currentJob, job.status.isTerminal {
                        ResearchResultSummaryView(job: job)
                    }

                    ArtifactListView(
                        title: "Report",
                        artifacts: viewModel.primaryArtifacts,
                        technicalArtifacts: [],
                        serverViewModel: serverViewModel
                    )

                    if !viewModel.evidenceArtifacts.isEmpty || !viewModel.technicalArtifacts.isEmpty {
                        ArtifactListView(
                            title: "Additional Results",
                            artifacts: viewModel.evidenceArtifacts,
                            technicalArtifacts: viewModel.technicalArtifacts,
                            serverViewModel: serverViewModel
                        )
                    }
                }
                .padding(.horizontal, horizontalPadding)
                .padding(.vertical, 38)
                .frame(minWidth: AppTheme.contentMinWidth, maxWidth: AppTheme.contentMaxWidth, alignment: .leading)
            }
            .scrollContentBackground(.hidden)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var researchModelChip: some View {
        HStack(spacing: 7) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 12, weight: .medium))
            Text("qwen3.5:4b")
                .font(.system(size: 13, weight: .semibold))
            Text("Research model")
                .font(.system(size: 12))
                .foregroundStyle(AppTheme.textSecondary)
        }
        .foregroundStyle(AppTheme.textPrimary)
        .padding(.horizontal, 10)
        .frame(height: 34)
        .glassSurface(fill: AppTheme.inputSurface.opacity(0.72), topFill: AppTheme.inputSurfaceTop.opacity(0.82), material: .thinMaterial, radius: 8, border: AppTheme.borderSubtle)
        .accessibilityLabel("qwen3.5:4b research model")
    }

    private var pdfDropZone: some View {
        VStack(spacing: 10) {
            Image(systemName: "doc.richtext")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(AppTheme.textSecondary)

            VStack(spacing: 4) {
                Text("Drop a research PDF here")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                Text(viewModel.selectedFileURL == nil ? "or choose a file from this Mac" : viewModel.selectedFilename)
                    .font(.system(size: 12, weight: viewModel.selectedFileURL == nil ? .regular : .medium))
                    .foregroundStyle(viewModel.selectedFileURL == nil ? AppTheme.textSecondary : AppTheme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Button {
                viewModel.choosePDF()
            } label: {
                Label("Choose PDF", systemImage: "plus")
            }
            .buttonStyle(SecondaryLaboratoryButtonStyle())
        }
        .frame(maxWidth: .infinity, minHeight: 174)
        .padding(18)
        .glassSurface(
            fill: AppTheme.dropSurfaceBottom.opacity(0.86),
            topFill: AppTheme.dropSurfaceTop.opacity(0.92),
            material: .thinMaterial,
            radius: AppTheme.composerRadius,
            border: viewModel.isDropTargeted ? AppTheme.accent.opacity(0.55) : AppTheme.borderStrong
        )
        .onDrop(of: [.fileURL], isTargeted: $viewModel.isDropTargeted) { providers in
            handleDrop(providers)
        }
        .accessibilityLabel("Drop a PDF for research analysis")
    }

    private var settingsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle(title: "Research Settings")

            Grid(alignment: .leading, horizontalSpacing: 30, verticalSpacing: 10) {
                GridRow {
                    Text("Document type")
                        .settingLabel()
                    pickerSurface {
                        Picker("Document type", selection: $viewModel.documentType) {
                            ForEach(ResearchDocumentType.allCases) { option in
                                Text(option.displayName).tag(option)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                    }
                }

                GridRow {
                    Text("Reading order")
                        .settingLabel()
                    pickerSurface {
                        Picker("Reading order", selection: $viewModel.readingOrder) {
                            ForEach(ResearchReadingOrder.allCases) { option in
                                Text(option.displayName).tag(option)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                    }
                }

                GridRow {
                    Text("Maximum chunk size")
                        .settingLabel()
                    Stepper(value: $viewModel.maxChunkChars, in: 500...4000, step: 100) {
                        Text("\(viewModel.maxChunkChars)")
                            .frame(width: 48, alignment: .trailing)
                            .monospacedDigit()
                            .foregroundStyle(AppTheme.textPrimary)
                    }
                    .padding(.horizontal, 8)
                    .frame(width: 104, height: 30)
                    .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 6, border: AppTheme.borderSubtle)
                }
            }
        }
    }

    private func pickerSurface<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .frame(width: 164, height: 30)
            .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 6, border: AppTheme.borderSubtle)
    }

    private var actionSection: some View {
        HStack {
            Spacer()
            Button {
                analyze()
            } label: {
                Label("Analyze Paper", systemImage: "doc.text.magnifyingglass")
            }
            .buttonStyle(PrimaryLaboratoryButtonStyle())
            .disabled(analyzeDisabled)
        }
    }

    private var analyzeDisabled: Bool {
        viewModel.selectedFileURL == nil || viewModel.isAnalyzing || !canAttemptResearch
    }

    private var canAttemptResearch: Bool {
        switch serverViewModel.connectionState {
        case .connected, .qwenUnavailable:
            true
        case .notConfigured, .connecting, .unreachable, .authenticationFailed, .failed:
            false
        }
    }

    private func analyze() {
        guard !analyzeDisabled else {
            return
        }
        Task {
            do {
                try await viewModel.analyze(using: serverViewModel.makeClient()) { job in
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
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) else {
            viewModel.errorMessage = "Choose a .pdf file for Research."
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
                    viewModel.errorMessage = "Choose a .pdf file for Research."
                    return
                }
                viewModel.selectFile(url)
            }
        }

        return true
    }
}

private struct ActiveResearchJobView: View {
    @Bindable var viewModel: ResearchViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Analyzing Research Paper")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text(viewModel.selectedFilename)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text("qwen3.5:4b · Research model")
                        .font(.system(size: 11.5))
                        .foregroundStyle(AppTheme.textTertiary)
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

            if viewModel.isAnalyzing {
                ProgressView()
                    .progressViewStyle(.linear)
            }
        }
        .padding(16)
        .laboratorySurface(fill: AppTheme.elevatedSurface.opacity(0.7), topFill: AppTheme.elevatedSurfaceTop.opacity(0.72), radius: 8, border: AppTheme.borderSubtle)
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
        if viewModel.currentJob?.status == .failed && isActive {
            return AppTheme.failure
        }
        if isComplete {
            return AppTheme.success
        }
        return isActive ? AppTheme.progress : AppTheme.textTertiary
    }
}

private struct ResearchResultSummaryView: View {
    let job: Job

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle(title: job.status == .failed ? "Research Failed" : "Research Results")

            VStack(spacing: 0) {
                summaryRow("Execution", value: job.status.displayName, color: job.status == .failed ? AppTheme.failure : AppTheme.textPrimary)

                if let research = job.research {
                    summaryRow("Research Quality", value: research.qualityDisplayName, color: qualityColor(research.status))
                    summaryRow("Document Type", value: research.documentTypeDisplayName)

                    if let accepted = research.accepted_records {
                        summaryRow("Accepted Evidence", value: "\(accepted)")
                    }
                    if let selected = research.selected_records {
                        summaryRow("Selected Evidence", value: "\(selected)")
                    }
                    if let rejected = research.rejected_attempts {
                        summaryRow("Rejected Attempts", value: "\(rejected)")
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(AppTheme.borderSubtle, lineWidth: 1)
            )

            if let message = explanatoryMessage {
                Text(message)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.warning)
                    .fixedSize(horizontal: false, vertical: true)
            }

            warningDetails
        }
    }

    @ViewBuilder
    private var warningDetails: some View {
        if let research = job.research {
            let details = (research.reasons ?? []) + (research.missing_coverage ?? []) + (research.source_quality_issues ?? [])
            if !details.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(details.prefix(5), id: \.self) { detail in
                        HStack(alignment: .firstTextBaseline, spacing: 7) {
                            Image(systemName: "exclamationmark.triangle")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(AppTheme.warning)
                            Text(detail)
                                .font(.system(size: 12.5))
                                .foregroundStyle(AppTheme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    private var explanatoryMessage: String? {
        if job.status == .failed {
            return job.error ?? "Research processing failed."
        }
        guard let status = job.research?.status else {
            return nil
        }
        switch status {
        case .partial:
            return "Research completed with partial coverage. Some sections could not be fully supported by extracted evidence."
        case .failed:
            return "Processing completed, but a reliable research report could not be produced."
        case .completed, .unknown:
            return nil
        }
    }

    private func summaryRow(_ label: String, value: String, color: Color = AppTheme.textPrimary) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 12.5))
                .foregroundStyle(AppTheme.textSecondary)
            Spacer()
            Text(value)
                .font(.system(size: 12.5, weight: .medium))
                .foregroundStyle(color)
        }
        .padding(.horizontal, 12)
        .frame(height: 34)
        .background(
            LinearGradient(
                colors: [AppTheme.elevatedSurfaceTop.opacity(0.38), AppTheme.elevatedSurface.opacity(0.38)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AppTheme.separator)
                .frame(height: 1)
        }
    }

    private func qualityColor(_ status: ResearchQualityStatus?) -> Color {
        switch status {
        case .completed:
            AppTheme.success
        case .partial:
            AppTheme.warning
        case .failed:
            AppTheme.failure
        case .unknown, nil:
            AppTheme.textSecondary
        }
    }
}

private struct MissingResearchModelView: View {
    let command: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(AppTheme.warning)
                Text("Research model unavailable")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
            }

            Text("The server does not currently have qwen3.5:4b installed. Run this on the server:")
                .font(.system(size: 12.5))
                .foregroundStyle(AppTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 10) {
                Text(command)
                    .font(.system(size: 12.5, design: .monospaced))
                    .foregroundStyle(AppTheme.textPrimary)
                    .padding(.horizontal, 10)
                    .frame(height: 32)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 6, border: AppTheme.borderSubtle)

                Button(copied ? "Copied" : "Copy Command") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(command, forType: .string)
                    copied = true
                }
                .buttonStyle(SecondaryLaboratoryButtonStyle())
            }
        }
        .padding(14)
        .laboratorySurface(fill: AppTheme.elevatedSurface.opacity(0.68), topFill: AppTheme.elevatedSurfaceTop.opacity(0.74), radius: 8, border: AppTheme.warning.opacity(0.28))
    }
}

private extension Text {
    func settingLabel() -> some View {
        self
            .font(.system(size: 13))
            .foregroundStyle(AppTheme.textSecondary)
            .frame(width: 190, alignment: .leading)
    }
}
