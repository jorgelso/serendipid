import SwiftUI
import SerendipidCore

/// Ports the web app's "Full analysis" `<details>` disclosure — raw
/// visual/audio/text analysis plus music/post_date/likes metadata. Renders
/// nothing if every field is empty.
struct FullAnalysisDisclosure: View {
    let post: Post
    @State private var isExpanded = false

    private var hasContent: Bool {
        !(post.visual_analysis ?? "").isEmpty
            || !(post.audio_transcription ?? "").isEmpty
            || !(post.text_analysis ?? "").isEmpty
            || !(post.music ?? "").isEmpty
            || post.post_date != nil
            || post.likes != nil
    }

    var body: some View {
        if hasContent {
            DisclosureGroup("Full analysis", isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 14) {
                    section(title: "Visual", text: post.visual_analysis)
                    section(title: "Audio transcription", text: post.audio_transcription)
                    section(title: "Text", text: post.text_analysis)

                    if let music = post.music, !music.isEmpty {
                        metadataRow(label: "Music", value: music)
                    }
                    if let postDate = post.post_date {
                        metadataRow(label: "Posted", value: postDate)
                    }
                    if let likes = post.likes {
                        metadataRow(label: "Likes", value: "\(likes)")
                    }
                }
                .padding(.top, 12)
            }
            .font(BrightPulseFont.body(size: 15, weight: .semibold))
            .foregroundStyle(BrightPulse.ink)
            .tint(BrightPulse.coral)
        }
    }

    @ViewBuilder
    private func section(title: String, text: String?) -> some View {
        if let text, !text.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(BrightPulseFont.body(size: 12, weight: .bold))
                    .foregroundStyle(BrightPulse.inkMuted)
                Text(text)
                    .font(BrightPulseFont.body(size: 14))
                    .foregroundStyle(BrightPulse.ink)
            }
        }
    }

    private func metadataRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(BrightPulseFont.body(size: 13, weight: .semibold))
                .foregroundStyle(BrightPulse.inkMuted)
            Spacer()
            Text(value)
                .font(BrightPulseFont.body(size: 13))
                .foregroundStyle(BrightPulse.ink)
        }
    }
}
