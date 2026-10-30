import SwiftUI

struct SidebarView: View {
    @Bindable var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 11) {
                SatelliteBrandIcon()
                    .frame(width: 24)
                Text("Satellites")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.textPrimary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 16)
            .padding(.top, 18)
            .padding(.bottom, 16)

            VStack(spacing: 2) {
                ForEach(AppSection.allCases) { section in
                    sidebarButton(section)
                }
            }
            .padding(.horizontal, 8)

            Spacer(minLength: 12)

            Rectangle()
                .fill(AppTheme.separator)
                .frame(height: 1)
                .padding(.horizontal, 10)

            SidebarServerStatusView(viewModel: appState.serverViewModel)
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 14)
        }
        .dockedPaneSurface(
            topFill: AppTheme.sidebarTop.opacity(0.96),
            bottomFill: AppTheme.sidebarBottom.opacity(0.97),
            material: .ultraThinMaterial
        )
    }

    private func sidebarButton(_ section: AppSection) -> some View {
        Button {
            appState.selectedSection = section
        } label: {
            HStack(spacing: 10) {
                Image(systemName: section.systemImage)
                    .font(.system(size: 13.5, weight: .medium))
                    .foregroundStyle(isSelected(section) ? AppTheme.textPrimary : Color(hex: 0x8F969B))
                    .frame(width: 18)
                Text(section.title)
                Spacer()
            }
            .font(.system(size: 13.5, weight: isSelected(section) ? .semibold : .medium))
            .padding(.horizontal, 12)
            .frame(height: 35)
            .contentShape(Rectangle())
            .background(
                Group {
                    if isSelected(section) {
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .fill(.thinMaterial)
                            .overlay(
                                RoundedRectangle(cornerRadius: 7, style: .continuous)
                                    .fill(
                                        LinearGradient(
                                            colors: [
                                                AppTheme.selectedSurface.opacity(0.76),
                                                AppTheme.selectedSurface.opacity(0.62)
                                            ],
                                            startPoint: .top,
                                            endPoint: .bottom
                                        )
                                    )
                            )
                            .overlay(alignment: .top) {
                                RoundedRectangle(cornerRadius: 7, style: .continuous)
                                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
                            }
                    }
                }
            )
        }
        .buttonStyle(.plain)
        .foregroundStyle(isSelected(section) ? AppTheme.textPrimary : Color(hex: 0xA8ADB1))
        .accessibilityLabel(section.title)
    }

    private func isSelected(_ section: AppSection) -> Bool {
        appState.selectedSection == section
    }
}

struct SidebarServerStatusView: View {
    @Bindable var viewModel: ServerViewModel

    var body: some View {
        Button {
            viewModel.showingSettings = true
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 7.5, height: 7.5)
                    Text(viewModel.connectionState.title)
                        .font(.system(size: 12.5, weight: .medium))
                        .foregroundStyle(AppTheme.textPrimary)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(AppTheme.textTertiary)
                }

                if case .connected(let health) = viewModel.connectionState {
                    VStack(alignment: .leading, spacing: 2) {
                        statusMetric("Qwen3 8B", health.qwen3_8b_available ? "Ready" : "Unavailable")
                        statusMetric("Workers", "\(health.worker_count)")
                        statusMetric("Rscript", health.Rscript ? "Available" : "Unavailable")
                    }
                } else {
                    Text(viewModel.connectionState.subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Server status: \(viewModel.connectionState.title)")
    }

    private func statusMetric(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(Color(hex: 0x858B90))
            Spacer()
            Text(value)
                .fontWeight(.medium)
                .foregroundStyle(Color(hex: 0xD4D6D7))
        }
        .font(.system(size: 11))
        .frame(height: 19)
    }

    private var statusColor: Color {
        switch viewModel.connectionState {
        case .connected:
            AppTheme.success
        case .connecting:
            AppTheme.warning
        case .qwenUnavailable:
            AppTheme.warning
        case .authenticationFailed, .unreachable, .failed:
            AppTheme.failure
        case .notConfigured:
            AppTheme.textTertiary
        }
    }
}
