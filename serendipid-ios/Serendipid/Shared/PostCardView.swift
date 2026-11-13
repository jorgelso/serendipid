import SwiftUI
import SerendipidCore

/// The core feed card — reused by Home, Browse, Search results, and
/// Insights' related-post lists. Single-column mobile feed (matching what
/// the web app's `minmax(260px, 1fr)` masonry grid actually collapses to at
/// phone width, not a cramped 2-up grid), with badge/tag rows that wrap via
/// `FlowLayout` instead of a fixed-width `HStack` that would otherwise
/// overflow the card. The thumbnail is a fixed height, not a width-scaled
/// aspect ratio — at nearly full screen width, a portrait aspect ratio (e.g.
/// 4:5) makes the image alone almost as tall as the whole screen, so only
/// one card is visible at a time.
struct PostCardView: View {
    let post: Post
    let baseURL: URL?
    var similarity: Double? = nil

    @Environment(AppDataStore.self) private var dataStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            thumbnail
            content
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(BrightPulse.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .strokeBorder(BrightPulse.line, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 4)
    }

    private var thumbnail: some View {
        ZStack(alignment: .topLeading) {
            ResolvedThumbnailImage(raw: post.thumbnail, baseURL: baseURL)
                .aspectRatio(contentMode: .fill)
                .frame(height: 190)
                .frame(maxWidth: .infinity)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            if let primaryCategory = post.category.first {
                LabelPill(primaryCategory)
                    .padding(8)
            }

            VStack {
                HStack {
                    Spacer()
                    VStack(alignment: .trailing, spacing: 4) {
                        if let similarity {
                            PillBadge("\(Int(similarity * 100))% match", background: BrightPulse.tealSoft, foreground: BrightPulse.tealInk)
                        }
                        if MediaResolver.isMissingVideo(post) {
                            PillBadge("no video", background: BrightPulse.surface2, foreground: BrightPulse.inkMuted)
                        }
                    }
                }
                Spacer()
                if post.needs_review, let currentVersion = dataStore.changelog?.current_version {
                    HStack {
                        Spacer()
                        VersionBehindBadge(versionsBehind: max(1, currentVersion - post.analysis_version))
                    }
                }
            }
            .padding(8)
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(post.title?.isEmpty == false ? post.title! : "Untitled reel")
                .font(BrightPulseFont.display(size: 16, weight: .semibold))
                .foregroundStyle(BrightPulse.ink)
                .lineLimit(1)
                .fixedSize(horizontal: false, vertical: true)

            Text("@\(post.username)")
                .font(BrightPulseFont.body(size: 13, weight: .semibold))
                .foregroundStyle(BrightPulse.inkMuted)

            if post.category.count > 1 || !post.language.isEmpty {
                FlowLayout(spacing: 5) {
                    ForEach(post.category.dropFirst(), id: \.self) { category in
                        LabelPill(category)
                    }
                    ForEach(post.language, id: \.self) { language in
                        PillBadge("🌐 \(language)", background: BrightPulse.surface2, foreground: BrightPulse.inkMuted, uppercase: false)
                    }
                }
            }

            if let summary = post.summary, !summary.isEmpty {
                Text(summary)
                    .font(BrightPulseFont.body(size: 13))
                    .foregroundStyle(BrightPulse.inkMuted)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !post.tags.isEmpty {
                tagRow
            }
        }
    }

    private var tagRow: some View {
        let visible = Array(post.tags.prefix(4))
        let remaining = post.tags.count - visible.count
        return FlowLayout(spacing: 5) {
            ForEach(visible, id: \.self) { tag in
                LabelPill(tag, uppercase: false)
            }
            if remaining > 0 {
                Text("+\(remaining)")
                    .font(BrightPulseFont.body(size: 11, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
    }
}
