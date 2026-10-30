import SwiftUI

struct PlaceholderView: View {
    let title: String
    let message: String
    let systemImage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: systemImage)
                .font(.largeTitle)
                .foregroundStyle(AppTheme.textSecondary)
            Text(title)
                .font(.system(size: 27, weight: .medium, design: .rounded))
                .foregroundStyle(AppTheme.textPrimary)
            Text(message)
                .font(.system(size: 15))
                .foregroundStyle(AppTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(.horizontal, AppTheme.contentInset)
        .padding(.vertical, 52)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(
            LinearGradient(
                colors: [AppTheme.mainBackgroundTop, AppTheme.mainBackgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }
}
