import SwiftUI

struct ContentView: View {
    @State private var appState = AppState()
    @State private var showingRecentJobsPopover = false
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        GeometryReader { proxy in
            let showsInspector = proxy.size.width >= AppTheme.inspectorCollapseBreakpoint
            let sidebarWidth = sidebarWidth(for: proxy.size.width)

            HStack(spacing: AppTheme.paneGap) {
                SidebarView(appState: appState)
                    .frame(width: sidebarWidth)
                    .padding(.leading, AppTheme.shellInset)
                    .padding(.vertical, AppTheme.shellInset)

                ZStack(alignment: .topTrailing) {
                    mainContent
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(
                            LinearGradient(
                                colors: [AppTheme.mainBackgroundTop, AppTheme.mainBackgroundBottom],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )

                    if !showsInspector {
                        Button {
                            showingRecentJobsPopover.toggle()
                        } label: {
                            Image(systemName: "clock.arrow.circlepath")
                                .font(.system(size: 15, weight: .semibold))
                                .frame(width: 34, height: 34)
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(AppTheme.textPrimary)
                        .laboratorySurface(fill: AppTheme.inputSurface, topFill: AppTheme.inputSurfaceTop, radius: 8, border: AppTheme.borderSubtle)
                        .padding(.top, 18)
                        .padding(.trailing, 18)
                        .accessibilityLabel("Show Recent Jobs")
                        .popover(isPresented: $showingRecentJobsPopover, arrowEdge: .trailing) {
                            RecentJobsView(
                                jobsViewModel: appState.jobsViewModel,
                                onSelectJob: { job in
                                    showingRecentJobsPopover = false
                                    appState.selectJob(job)
                                },
                                onNewTask: {
                                    showingRecentJobsPopover = false
                                    appState.selectedSection = .chat
                                }
                            )
                            .frame(width: AppTheme.inspectorWidth, height: 520)
                        }
                    }
                }
                .frame(minWidth: AppTheme.centerMinWidth)

                if showsInspector {
                    RecentJobsView(
                        jobsViewModel: appState.jobsViewModel,
                        onSelectJob: appState.selectJob,
                        onNewTask: {
                            appState.selectedSection = .chat
                        }
                    )
                    .frame(
                        minWidth: AppTheme.inspectorMinWidth,
                        idealWidth: AppTheme.inspectorWidth,
                        maxWidth: AppTheme.inspectorMaxWidth
                    )
                    .padding(.trailing, AppTheme.shellInset)
                    .padding(.vertical, AppTheme.shellInset)
                }
            }
            .background(
                LinearGradient(
                    colors: [AppTheme.titlebarBackground, AppTheme.mainBackgroundBottom],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
        }
        .frame(minWidth: 820, minHeight: 680)
        .task {
            await appState.serverViewModel.refreshConnectionIfConfigured()
            await refreshJobsIfPossible()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task {
                    await appState.serverViewModel.refreshConnectionIfStale()
                    await refreshJobsIfPossible()
                }
            }
        }
        .onChange(of: appState.selectedSection) { _, section in
            if section == .jobs {
                Task {
                    await refreshJobsIfPossible()
                }
            }
        }
        .sheet(isPresented: Bindable(appState.serverViewModel).showingSettings) {
            ServerSettingsView(viewModel: appState.serverViewModel, memoryViewModel: appState.memoryViewModel) {
                Task {
                    await refreshJobsIfPossible()
                }
            }
            .frame(width: 520)
        }
    }

    @ViewBuilder
    private var mainContent: some View {
        switch appState.selectedSection {
        case .chat:
            ChatView(
                appState: appState,
                viewModel: appState.chatViewModel,
                serverViewModel: appState.serverViewModel
            )
        case .jobs:
            JobsView(
                serverViewModel: appState.serverViewModel,
                viewModel: appState.jobsViewModel
            )
        case .research:
            ResearchView(
                serverViewModel: appState.serverViewModel,
                jobsViewModel: appState.jobsViewModel,
                viewModel: appState.researchViewModel
            )
        case .flashcards:
            FlashcardsView(
                serverViewModel: appState.serverViewModel,
                jobsViewModel: appState.jobsViewModel,
                viewModel: appState.flashcardsViewModel
            )
        case .files:
            PlaceholderView(
                title: "Files",
                message: "File history will be added in a later milestone.",
                systemImage: "folder"
            )
        }
    }

    private func sidebarWidth(for totalWidth: CGFloat) -> CGFloat {
        if totalWidth < AppTheme.inspectorCollapseBreakpoint {
            return AppTheme.sidebarMinWidth
        }
        return AppTheme.sidebarWidth
    }

    private func refreshJobsIfPossible() async {
        guard case .connected = appState.serverViewModel.connectionState,
              let client = try? appState.serverViewModel.makeClient()
        else {
            return
        }
        await appState.jobsViewModel.refresh(using: client)
    }
}

#Preview {
    ContentView()
}
