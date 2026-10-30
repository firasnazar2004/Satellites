import SwiftUI

struct RecentJobsView: View {
    @Bindable var jobsViewModel: JobsViewModel
    let onSelectJob: (Job) -> Void
    let onNewTask: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            filterBar

            Rectangle()
                .fill(AppTheme.separator)
                .frame(height: 1)

            if jobsViewModel.recentJobs.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "clock")
                        .font(.title2)
                        .foregroundStyle(AppTheme.textTertiary)
                    Text("No Recent Jobs")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.textPrimary)
                    Text("Server jobs will appear here.")
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(18)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(jobsViewModel.recentJobs) { job in
                            Button {
                                onSelectJob(job)
                            } label: {
                                RecentJobRow(job: job)
                            }
                            .buttonStyle(.plain)

                            Rectangle()
                                .fill(AppTheme.separator)
                                .frame(height: 1)
                                .padding(.leading, 44)
                        }
                    }
                }
            }
        }
        .dockedPaneSurface(
            topFill: AppTheme.inspectorTop.opacity(0.96),
            bottomFill: AppTheme.inspectorBottom.opacity(0.97),
            material: .thinMaterial
        )
    }

    private var header: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.textSecondary)
                TextField("Search jobs...", text: $jobsViewModel.searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.textPrimary)
            }
            .padding(.horizontal, 10)
            .frame(height: 35)
            .frame(minWidth: 0, maxWidth: .infinity)
            .glassSurface(fill: AppTheme.elevatedSurface.opacity(0.72), topFill: AppTheme.elevatedSurfaceTop.opacity(0.82), material: .thinMaterial, radius: 8, border: AppTheme.borderSubtle)

            Button(action: onNewTask) {
                Image(systemName: "plus")
                    .font(.system(size: 17, weight: .medium))
                    .frame(width: 34, height: 34)
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color(hex: 0xDADCDD))
            .glassSurface(fill: AppTheme.inputSurface.opacity(0.76), topFill: AppTheme.inputSurfaceTop.opacity(0.86), material: .thinMaterial, radius: 8, border: AppTheme.borderSubtle)
            .accessibilityLabel("New Task")
        }
        .padding(.horizontal, 16)
        .padding(.top, 30)
        .padding(.bottom, 12)
    }

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 5) {
                ForEach(JobFilter.allCases) { filter in
                    Button {
                        jobsViewModel.filter = filter
                    } label: {
                        Text(filter.title)
                            .font(.system(size: 11.5, weight: jobsViewModel.filter == filter ? .semibold : .medium))
                            .foregroundStyle(jobsViewModel.filter == filter ? AppTheme.textPrimary : AppTheme.textSecondary)
                            .padding(.horizontal, 9)
                            .frame(height: 28)
                            .background(
                                RoundedRectangle(cornerRadius: 6, style: .continuous)
                                    .fill(jobsViewModel.filter == filter ? Color(hex: 0x34383C) : Color.clear)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 10)
    }
}

private struct RecentJobRow: View {
    let job: Job

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            StatusIcon(status: job.status)
                .padding(.top, 3)

            VStack(alignment: .leading, spacing: 3) {
                Text(job.displayLabel)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color(hex: 0xE7E9EA))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(job.pipeline.displayName)
                    .font(.system(size: 11.5))
                    .foregroundStyle(AppTheme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }

            Spacer(minLength: 8)

            Text(DateDisplay.relative(job.bestActivityDate))
                .font(.system(size: 11))
                .foregroundStyle(Color(hex: 0x8B9094))
                .lineLimit(1)
                .frame(width: 58, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .frame(height: 66)
        .contentShape(Rectangle())
    }
}
