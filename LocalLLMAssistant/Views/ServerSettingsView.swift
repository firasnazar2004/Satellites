import SwiftUI

struct ServerSettingsView: View {
    @Bindable var viewModel: ServerViewModel
    @Bindable var memoryViewModel: MemoryViewModel
    var onConnectionUpdated: (() -> Void)?

    @Environment(\.dismiss) private var dismiss
    @State private var showingClearMemoryConfirmation = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text("Settings")
                    .font(.system(size: 22, weight: .medium, design: .rounded))
                    .foregroundStyle(AppTheme.textPrimary)

                serverSection
                memorySection

                HStack {
                    Button("Save") {
                        viewModel.save()
                        dismiss()
                    }
                    .buttonStyle(PrimaryLaboratoryButtonStyle())
                    .keyboardShortcut(.defaultAction)

                    Button {
                        Task {
                            await viewModel.testConnection()
                            onConnectionUpdated?()
                        }
                    } label: {
                        if viewModel.connectionState == .connecting {
                            ProgressView()
                                .controlSize(.small)
                        } else {
                            Label("Test Connection", systemImage: "network")
                        }
                    }
                    .buttonStyle(SecondaryLaboratoryButtonStyle())
                    .disabled(viewModel.connectionState == .connecting)

                    Spacer()

                    Button("Done") {
                        dismiss()
                    }
                    .buttonStyle(SecondaryLaboratoryButtonStyle())
                }
            }
            .padding(24)
        }
        .scrollContentBackground(.hidden)
        .background(.thinMaterial)
        .background(AppTheme.mainBackground.opacity(0.92))
        .task {
            await memoryViewModel.load()
        }
        .confirmationDialog(
            "Clear all Shaka memories?",
            isPresented: $showingClearMemoryConfirmation,
            titleVisibility: .visible
        ) {
            Button("Clear All", role: .destructive) {
                Task {
                    await memoryViewModel.clearAll()
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes everything you've explicitly asked Shaka to remember. This cannot be undone.")
        }
    }

    private var serverSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(title: "Server")

            Text("Server URL")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(AppTheme.textSecondary)
            TextField("http://100.x.x.x:8000", text: $viewModel.serverURLString)
                .textFieldStyle(.roundedBorder)

            Text("API Key")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(AppTheme.textSecondary)
            SecureField("Required for remote access", text: $viewModel.apiKey)
                .textFieldStyle(.roundedBorder)

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.failure)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var memorySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    SectionTitle(title: "Shaka Memory")
                    Text("Shaka remembers only things you've explicitly asked it to remember.")
                        .font(.system(size: 12.5))
                        .foregroundStyle(AppTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer()

                Button("Clear All Memories", role: .destructive) {
                    showingClearMemoryConfirmation = true
                }
                .buttonStyle(SecondaryLaboratoryButtonStyle())
                .disabled(memoryViewModel.memories.isEmpty)
            }

            if memoryViewModel.isLoading {
                ProgressView()
                    .controlSize(.small)
            } else if memoryViewModel.memories.isEmpty {
                Text("No saved memories yet.")
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.textSecondary)
                    .padding(.vertical, 4)
            } else {
                VStack(spacing: 0) {
                    ForEach(memoryViewModel.memories) { memory in
                        MemoryRow(memory: memory) {
                            Task {
                                await memoryViewModel.delete(memory)
                            }
                        }

                        if memory.id != memoryViewModel.memories.last?.id {
                            Rectangle()
                                .fill(AppTheme.separator)
                                .frame(height: 1)
                                .padding(.leading, 12)
                        }
                    }
                }
                .glassSurface(
                    fill: AppTheme.elevatedSurface.opacity(0.55),
                    topFill: AppTheme.elevatedSurfaceTop.opacity(0.62),
                    material: .thinMaterial,
                    radius: 8,
                    border: AppTheme.borderSubtle
                )
            }

            if let savedMessage = memoryViewModel.savedMessage {
                Text(savedMessage)
                    .font(.system(size: 12.5))
                    .foregroundStyle(AppTheme.success)
            }

            if let errorMessage = memoryViewModel.errorMessage {
                Text(errorMessage)
                    .font(.system(size: 12.5))
                    .foregroundStyle(AppTheme.failure)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct MemoryRow: View {
    let memory: MemoryItem
    let onDelete: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(memory.content)
                    .font(.system(size: 13))
                    .foregroundStyle(AppTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(memory.createdAt, style: .date)
                    .font(.system(size: 11.5))
                    .foregroundStyle(AppTheme.textTertiary)
            }

            Spacer()

            Button(role: .destructive, action: onDelete) {
                Image(systemName: "trash")
                    .font(.system(size: 12, weight: .medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(AppTheme.failure)
            .accessibilityLabel("Delete memory")
        }
        .padding(12)
    }
}
