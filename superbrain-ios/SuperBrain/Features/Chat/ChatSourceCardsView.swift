import SwiftUI
import SuperBrainCore

/// Source citation cards under an assistant message — thumbnail resolved
/// directly from the already-cached `Post` by shortcode (no
/// `/api/thumbnail/{shortcode}` proxy needed the way the web app has, since
/// there's no HTML-payload-size concern natively).
struct ChatSourceCardsView: View {
    let sources: [ChatSource]

    @Environment(AppDataStore.self) private var dataStore
    @Environment(\.configStore) private var configStore
    @State private var isExpanded = false

    var body: some View {
        if !sources.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Button(isExpanded ? "Hide sources" : "Show sources (\(sources.count))") {
                    isExpanded.toggle()
                }
                .font(BrightPulseFont.body(size: 12, weight: .semibold))
                .foregroundStyle(BrightPulse.coralInk)

                if isExpanded {
                    ForEach(sources) { source in
                        sourceCard(source)
                    }
                }
            }
        }
    }

    private func sourceCard(_ source: ChatSource) -> some View {
        let thumbnail = dataStore.post(shortcode: source.shortcode)?.thumbnail

        return NavigationLink(value: source.shortcode) {
            HStack(spacing: 10) {
                ResolvedThumbnailImage(raw: thumbnail, baseURL: configStore.baseURL)
                    .frame(width: 44, height: 44)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                VStack(alignment: .leading, spacing: 2) {
                    Text(source.title.isEmpty ? "Untitled reel" : source.title)
                        .font(BrightPulseFont.body(size: 13, weight: .semibold))
                        .foregroundStyle(BrightPulse.ink)
                        .lineLimit(1)
                    Text("@\(source.username) · \(Int(source.similarity * 100))% match")
                        .font(BrightPulseFont.body(size: 11))
                        .foregroundStyle(BrightPulse.inkMuted)
                }
                Spacer()
            }
            .padding(8)
            .background(BrightPulse.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}
