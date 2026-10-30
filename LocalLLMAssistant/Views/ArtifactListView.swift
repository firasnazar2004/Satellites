import SwiftUI

struct ArtifactListView: View {
    let title: String
    let artifacts: [Artifact]
    var technicalArtifacts: [Artifact] = []
    let serverViewModel: ServerViewModel

    @State private var errorMessage: String?
    @State private var savedMessage: String?
    @State private var showingTechnicalArtifacts = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: title)

            if artifacts.isEmpty && technicalArtifacts.isEmpty {
                Text("Artifacts will appear after the job completes.")
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.textSecondary)
            } else {
                artifactRows(artifacts)

                if !technicalArtifacts.isEmpty {
                    DisclosureGroup("Show Technical Artifacts", isExpanded: $showingTechnicalArtifacts) {
                        artifactRows(technicalArtifacts)
                            .padding(.top, 8)
                    }
                }
            }

            if let savedMessage {
                Text(savedMessage)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.success)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.failure)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func artifactRows(_ artifacts: [Artifact]) -> some View {
        VStack(spacing: 0) {
            ForEach(artifacts) { artifact in
                HStack {
                    Image(systemName: icon(for: artifact))
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(width: 18)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(artifact.name)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(AppTheme.textPrimary)
                        Text(metadata(for: artifact))
                            .font(.system(size: 11.5))
                            .foregroundStyle(AppTheme.textSecondary)
                    }
                    Spacer()
                    Button {
                        Task {
                            await save(artifact)
                        }
                    } label: {
                        Label("Save", systemImage: "square.and.arrow.down")
                    }
                    .buttonStyle(SecondaryLaboratoryButtonStyle())
                }
                .padding(.horizontal, 12)
                .frame(height: 54)
                .background(
                    LinearGradient(
                        colors: [AppTheme.elevatedSurfaceTop.opacity(0.42), AppTheme.elevatedSurface.opacity(0.42)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                Rectangle()
                    .fill(AppTheme.separator)
                    .frame(height: 1)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(AppTheme.borderSubtle, lineWidth: 1)
        )
    }

    private func save(_ artifact: Artifact) async {
        errorMessage = nil
        savedMessage = nil
        do {
            let client = try serverViewModel.makeClient()
            let data = try await client.downloadArtifact(artifact)
            let panel = NSSavePanel()
            panel.nameFieldStringValue = artifact.name

            guard panel.runModal() == .OK, let destination = panel.url else {
                return
            }

            try data.write(to: destination, options: .atomic)
            savedMessage = "Saved \(artifact.name)."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func icon(for artifact: Artifact) -> String {
        if artifact.name.lowercased().hasSuffix(".csv") {
            return "tablecells"
        }
        if artifact.name.lowercased().hasSuffix(".json") {
            return "curlybraces"
        }
        if artifact.name.lowercased().hasSuffix(".log") {
            return "terminal"
        }
        return "doc"
    }

    private func metadata(for artifact: Artifact) -> String {
        let type = artifact.name.split(separator: ".").last.map { String($0).uppercased() } ?? "File"
        switch artifact.classification {
        case .primaryResult:
            return "\(type) · Primary result"
        case .secondaryResult:
            return type
        case .technical:
            return "\(type) · Technical"
        }
    }
}
