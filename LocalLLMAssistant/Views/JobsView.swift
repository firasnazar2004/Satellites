import SwiftUI

struct JobsView: View {
    let serverViewModel: ServerViewModel
    @Bindable var viewModel: JobsViewModel

    var body: some View {
        VStack(spacing: 0) {
            header
            Rectangle()
                .fill(AppTheme.separator)
                .frame(height: 1)

            HStack(spacing: 0) {
                jobList
                    .frame(minWidth: 420)

                Rectangle()
                    .fill(AppTheme.separator)
                    .frame(width: 1)

                JobDetailView(
                    serverViewModel: serverViewModel,
                    job: viewModel.selectedJob
                )
                .frame(minWidth: 320)
            }
        }
    }

    private var header: some View {
        HStack {
            PageHeader(title: "Jobs", subtitle: "Recent work from the FastAPI job store.")

            Spacer()

            Picker("Filter", selection: $viewModel.filter) {
                ForEach(JobFilter.allCases) { filter in
                    Text(filter.title).tag(filter)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 340)

            Button {
                Task {
                    if let client = try? serverViewModel.makeClient() {
                        await viewModel.refresh(using: client)
                    }
                }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(SecondaryLaboratoryButtonStyle())
            .disabled(viewModel.isRefreshing)
        }
        .padding(.horizontal, AppTheme.contentInset)
        .padding(.vertical, 24)
    }

    private var jobList: some View {
        VStack(spacing: 0) {
            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.callout)
                    .foregroundStyle(AppTheme.failure)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding([.horizontal, .top], 16)
            }

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(viewModel.filteredJobs) { job in
                        Button {
                            viewModel.selectedJobID = job.id
                        } label: {
                            JobRowView(job: job)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(viewModel.selectedJobID == job.id ? AppTheme.selectedSurface.opacity(0.35) : Color.clear)
                                )
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal, 16)

                        Rectangle()
                            .fill(AppTheme.separator)
                            .frame(height: 1)
                            .padding(.leading, 58)
                    }
                }
                .padding(.vertical, 12)
            }
            .overlay {
                if viewModel.filteredJobs.isEmpty {
                    ContentUnavailableView(
                        "No Jobs",
                        systemImage: "tray",
                        description: Text("Jobs will appear after the server returns them from /jobs.")
                    )
                    .foregroundStyle(AppTheme.textSecondary)
                }
            }
        }
    }
}

struct JobRowView: View {
    let job: Job

    var body: some View {
        HStack(spacing: 12) {
            StatusIcon(status: job.status)

            VStack(alignment: .leading, spacing: 3) {
                Text(job.displayLabel)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                Text("\(job.pipeline.displayName) · \(DateDisplay.relative(job.bestActivityDate))")
                    .font(.system(size: 12))
                    .foregroundStyle(AppTheme.textSecondary)
            }

            Spacer()

            Text(job.status.displayName)
                .font(.system(size: 11))
                .foregroundStyle(AppTheme.textSecondary)
        }
        .frame(height: 52)
        .contentShape(Rectangle())
    }
}

struct StatusIcon: View {
    let status: JobStatus

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: 14, weight: .medium))
            .foregroundStyle(color)
            .frame(width: 18)
    }

    private var systemImage: String {
        switch status {
        case .pending:
            "clock"
        case .running:
            "circle.dotted"
        case .completed:
            "checkmark.circle.fill"
        case .failed:
            "exclamationmark.circle.fill"
        }
    }

    private var color: Color {
        switch status {
        case .pending:
            AppTheme.textTertiary
        case .running:
            AppTheme.progress
        case .completed:
            AppTheme.success.opacity(0.9)
        case .failed:
            AppTheme.failure
        }
    }
}
