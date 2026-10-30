import SwiftUI

struct SatelliteBrandIcon: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 3.5)
                .stroke(AppTheme.textPrimary, lineWidth: 1.6)
                .frame(width: 9, height: 12)
                .rotationEffect(.degrees(-18))

            panel(offset: CGSize(width: -9, height: -3), rotation: -18)
            panel(offset: CGSize(width: 9, height: 3), rotation: -18)

            Path { path in
                path.move(to: CGPoint(x: 15, y: 7))
                path.addLine(to: CGPoint(x: 21, y: 1))
                path.move(to: CGPoint(x: 16, y: 8))
                path.addLine(to: CGPoint(x: 22, y: 9))
            }
            .stroke(AppTheme.textPrimary.opacity(0.88), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
        }
        .frame(width: 24, height: 24)
        .accessibilityHidden(true)
    }

    private func panel(offset: CGSize, rotation: Double) -> some View {
        RoundedRectangle(cornerRadius: 1.8)
            .stroke(AppTheme.textPrimary.opacity(0.9), lineWidth: 1.4)
            .frame(width: 10, height: 7)
            .rotationEffect(.degrees(rotation))
            .offset(offset)
    }
}
