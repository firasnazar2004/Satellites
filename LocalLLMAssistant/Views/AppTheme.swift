import SwiftUI

enum AppTheme {
    static let windowBackground = Color(hex: 0x161719)
    static let titlebarBackground = Color(hex: 0x1B1D1F)
    static let mainBackground = Color(hex: 0x1C1E20)
    static let mainBackgroundTop = Color(hex: 0x1E2022)
    static let mainBackgroundBottom = Color(hex: 0x181A1C)
    static let sidebarBackground = Color(hex: 0x1D1F20)
    static let sidebarTop = Color(hex: 0x202223)
    static let sidebarBottom = Color(hex: 0x1B1D1E)
    static let inspectorBackground = Color(hex: 0x1C1E1F)
    static let inspectorTop = Color(hex: 0x1F2122)
    static let inspectorBottom = Color(hex: 0x1A1C1D)
    static let elevatedSurface = Color(hex: 0x2C2F32)
    static let elevatedSurfaceTop = Color(hex: 0x303337)
    static let inputSurface = Color(hex: 0x292D30)
    static let inputSurfaceTop = Color(hex: 0x2C3034)
    static let dropSurfaceTop = Color(hex: 0x222528)
    static let dropSurfaceBottom = Color(hex: 0x1F2224)
    static let hoverSurface = Color(hex: 0x33373A)
    static let selectedSurface = Color(hex: 0x536B78)

    static let textPrimary = Color(hex: 0xF0F0F1)
    static let textSecondary = Color(hex: 0x989DA1)
    static let textTertiary = Color(hex: 0x6F7479)

    static let accent = Color(hex: 0x5E8C8A)
    static let accentHover = Color(hex: 0x6FA3A0)
    static let success = Color(hex: 0x45C86A)
    static let progress = Color(hex: 0x68A6C8)
    static let failure = Color(hex: 0xD56666)
    static let warning = Color(hex: 0xD8B35A)

    static let borderStrong = Color.white.opacity(0.10)
    static let borderSubtle = Color.white.opacity(0.075)
    static let paneBorder = Color.white.opacity(0.055)
    static let paneShadow = Color.black.opacity(0.16)
    static let separator = Color.white.opacity(0.055)
    static let topHighlight = Color.white.opacity(0.04)

    static let shellInset: CGFloat = 8
    static let paneGap: CGFloat = 8
    static let structuralPaneRadius: CGFloat = 12

    static let sidebarMinWidth: CGFloat = 210
    static let sidebarWidth: CGFloat = 240
    static let sidebarMaxWidth: CGFloat = 260
    static let centerMinWidth: CGFloat = 520
    static let inspectorMinWidth: CGFloat = 280
    static let inspectorWidth: CGFloat = 305
    static let inspectorMaxWidth: CGFloat = 330
    static let inspectorCollapseBreakpoint: CGFloat = 1120
    static let contentInset: CGFloat = 40
    static let compactContentInset: CGFloat = 28
    static let contentMaxWidth: CGFloat = 700
    static let contentMinWidth: CGFloat = 460
    static let radius: CGFloat = 8
    static let composerRadius: CGFloat = 10
}

extension Color {
    init(hex: UInt, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}

struct DockedPaneSurface: ViewModifier {
    var topFill: Color
    var bottomFill: Color
    var material: Material = .ultraThinMaterial
    var radius: CGFloat = AppTheme.structuralPaneRadius

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)

        content
            .background(material)
            .background(
                LinearGradient(
                    colors: [topFill, bottomFill],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .clipShape(shape)
            .overlay(
                shape.stroke(AppTheme.paneBorder, lineWidth: 1)
            )
            .overlay(alignment: .top) {
                shape
                    .stroke(Color.white.opacity(0.035), lineWidth: 1)
                    .blendMode(.screen)
            }
            .shadow(color: AppTheme.paneShadow, radius: 10, x: 0, y: 2)
    }
}

struct GlassSurface: ViewModifier {
    var fill: Color = AppTheme.elevatedSurface.opacity(0.7)
    var topFill: Color? = AppTheme.elevatedSurfaceTop.opacity(0.78)
    var material: Material = .thinMaterial
    var radius: CGFloat = AppTheme.radius
    var border: Color = AppTheme.borderSubtle
    var showsTopHighlight = true

    func body(content: Content) -> some View {
        content
            .background(material)
            .background(
                LinearGradient(
                    colors: [topFill ?? fill, fill],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .stroke(border, lineWidth: 1)
            )
            .overlay(alignment: .top) {
                if showsTopHighlight {
                    RoundedRectangle(cornerRadius: radius)
                        .stroke(AppTheme.topHighlight, lineWidth: 1)
                        .blendMode(.screen)
                }
            }
    }
}

struct LaboratorySurface: ViewModifier {
    var fill: Color = AppTheme.elevatedSurface
    var topFill: Color?
    var radius: CGFloat = AppTheme.radius
    var border: Color = AppTheme.borderSubtle
    var showsTopHighlight = true

    func body(content: Content) -> some View {
        content
            .background(
                LinearGradient(
                    colors: [topFill ?? fill, fill],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .stroke(border, lineWidth: 1)
            )
            .overlay(alignment: .top) {
                if showsTopHighlight {
                    RoundedRectangle(cornerRadius: radius)
                        .stroke(AppTheme.topHighlight, lineWidth: 1)
                        .blendMode(.screen)
                }
            }
    }
}

extension View {
    func dockedPaneSurface(
        topFill: Color,
        bottomFill: Color,
        material: Material = .ultraThinMaterial,
        radius: CGFloat = AppTheme.structuralPaneRadius
    ) -> some View {
        modifier(DockedPaneSurface(topFill: topFill, bottomFill: bottomFill, material: material, radius: radius))
    }

    func laboratorySurface(
        fill: Color = AppTheme.elevatedSurface,
        topFill: Color? = nil,
        radius: CGFloat = AppTheme.radius,
        border: Color = AppTheme.borderSubtle,
        showsTopHighlight: Bool = true
    ) -> some View {
        modifier(LaboratorySurface(fill: fill, topFill: topFill, radius: radius, border: border, showsTopHighlight: showsTopHighlight))
    }

    func glassSurface(
        fill: Color = AppTheme.elevatedSurface.opacity(0.7),
        topFill: Color? = AppTheme.elevatedSurfaceTop.opacity(0.78),
        material: Material = .thinMaterial,
        radius: CGFloat = AppTheme.radius,
        border: Color = AppTheme.borderSubtle,
        showsTopHighlight: Bool = true
    ) -> some View {
        modifier(GlassSurface(fill: fill, topFill: topFill, material: material, radius: radius, border: border, showsTopHighlight: showsTopHighlight))
    }
}

struct PrimaryLaboratoryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(AppTheme.textPrimary)
            .padding(.horizontal, 14)
            .frame(height: 36)
            .background(
                LinearGradient(
                    colors: [
                        configuration.isPressed ? AppTheme.accent.opacity(0.82) : AppTheme.accentHover.opacity(0.82),
                        configuration.isPressed ? AppTheme.accent.opacity(0.76) : AppTheme.accent
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(Color.white.opacity(0.075), lineWidth: 1)
            )
            .overlay(alignment: .top) {
                RoundedRectangle(cornerRadius: 7)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
            }
    }
}

struct SecondaryLaboratoryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(AppTheme.textPrimary)
            .padding(.horizontal, 12)
            .frame(height: 32)
            .glassSurface(
                fill: configuration.isPressed ? AppTheme.hoverSurface.opacity(0.82) : AppTheme.elevatedSurface.opacity(0.72),
                topFill: configuration.isPressed ? AppTheme.hoverSurface.opacity(0.88) : AppTheme.elevatedSurfaceTop.opacity(0.78),
                material: .thinMaterial,
                radius: 7,
                border: AppTheme.borderSubtle
            )
    }
}

struct SectionTitle: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(AppTheme.textPrimary)
    }
}

struct PageHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 27, weight: .medium, design: .rounded))
                .foregroundStyle(AppTheme.textPrimary)
            Text(subtitle)
                .font(.system(size: 14.5))
                .foregroundStyle(AppTheme.textSecondary)
        }
    }
}
