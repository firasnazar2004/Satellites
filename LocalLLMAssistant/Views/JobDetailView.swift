import SwiftUI

struct JobDetailView: View {
    let serverViewModel: ServerViewModel
    let job: Job?

    var body: some View {
        Group {
            if let job {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(job.displayLabel)
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundStyle(AppTheme.textPrimary)
                            Label(job.status.displayName, systemImage: "smallcircle.filled.circle")
                                .foregroundStyle(statusColor(job.status))
                        }

                        VStack(alignment: .leading, spacing: 12) {
                            SectionTitle(title: "Details")
                            detailGrid(job)
                        }
                        .padding(16)
                        .laboratorySurface(fill: AppTheme.elevatedSurface.opacity(0.65), topFill: AppTheme.elevatedSurfaceTop.opacity(0.65), radius: 8, border: AppTheme.borderSubtle)

                        if let error = job.error, !error.isEmpty {
                            DisclosureGroup("Error Details") {
                                Text(error)
                                    .font(.callout.monospaced())
                                    .foregroundStyle(AppTheme.textSecondary)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.top, 6)
                            }
                            .foregroundStyle(AppTheme.textPrimary)
                        }

                        ArtifactListView(
                            title: "Artifacts",
                            artifacts: job.artifacts,
                            serverViewModel: serverViewModel
                        )
                    }
                    .padding(22)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                ContentUnavailableView(
                    "No Job Selected",
                    systemImage: "list.bullet.rectangle",
                    description: Text("Select a job to inspect status and artifacts.")
                )
            }
        }
        .background(
            LinearGradient(
                colors: [AppTheme.mainBackgroundTop, AppTheme.mainBackgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    private func detailGrid(_ job: Job) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
            detailRow("Pipeline", job.pipeline.displayName)
            detailRow("Job ID", job.id)
            detailRow("Created", DateDisplay.absoluteFormatter.string(from: job.created_at))
            detailRow("Started", job.started_at.map(DateDisplay.absoluteFormatter.string(from:)) ?? "Not started")
            detailRow("Finished", job.finished_at.map(DateDisplay.absoluteFormatter.string(from:)) ?? "Not finished")
            detailRow("Elapsed", DateDisplay.duration(job.elapsedInterval))
        }
        .font(.callout)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        GridRow {
            Text(label)
                .foregroundStyle(AppTheme.textSecondary)
            Text(value)
                .textSelection(.enabled)
                .foregroundStyle(AppTheme.textPrimary)
        }
    }

    private func statusColor(_ status: JobStatus) -> Color {
        switch status {
        case .pending:
            AppTheme.textTertiary
        case .running:
            AppTheme.progress
        case .completed:
            AppTheme.success
        case .failed:
            AppTheme.failure
        }
    }
}
