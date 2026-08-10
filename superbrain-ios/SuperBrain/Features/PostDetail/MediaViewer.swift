import SwiftUI
import AVKit
import SuperBrainCore

/// Video/image/carousel viewer for a post's downloaded media — ports the web
/// app's `MediaViewer`. Falls back to explanatory copy (not a broken player)
/// when nothing was downloaded, distinguishing "Instagram post missing its
/// video" (offer to re-fetch) from "this content type never stores local
/// media" (link to the original instead).
struct MediaViewer: View {
    let post: Post
    let baseURL: URL?
    var onReanalyze: (() -> Void)?

    private var classified: MediaResolver.ClassifiedMedia {
        guard let baseURL else { return MediaResolver.ClassifiedMedia(videos: [], images: []) }
        let resolved = MediaResolver.resolveMediaURLs(post.media_urls, baseURL: baseURL)
        return MediaResolver.classifyMedia(resolved)
    }

    /// The backend always saves a `thumbnail.jpg` poster frame alongside a
    /// real `video.mp4` for the same reel — it's cover art, not separate
    /// gallery content, so it shouldn't appear as its own swipeable page once
    /// the real video is present (was showing up as a confusing second
    /// "image" page after the video, per real backend data: every Instagram
    /// post's `media_urls` includes both `video.mp4` and `thumbnail.jpg`).
    private func carouselItems(from media: MediaResolver.ClassifiedMedia) -> [MediaItem] {
        let hasVideo = !media.videos.isEmpty
        let images = media.images.filter { url in
            guard hasVideo else { return true }
            return url.deletingPathExtension().lastPathComponent.lowercased() != "thumbnail"
        }
        return media.videos.map { .video($0) } + images.map { .image($0) }
    }

    var body: some View {
        if MediaResolver.isMissingVideo(post) {
            missingVideoState
        } else {
            let items = carouselItems(from: classified)
            if items.isEmpty {
                noLocalCopyState
            } else {
                Carousel(items: items)
            }
        }
    }

    private var missingVideoState: some View {
        VStack(spacing: 10) {
            Text("Video not downloaded")
                .font(BrightPulseFont.body(size: 14, weight: .semibold))
                .foregroundStyle(BrightPulse.yellowInk)
            if let onReanalyze {
                PillButton("Re-fetch video", style: .secondary, action: onReanalyze)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(BrightPulse.yellowSoft)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var noLocalCopyState: some View {
        VStack(spacing: 8) {
            Text("No local copy is stored for this kind of post.")
                .font(BrightPulseFont.body(size: 14))
                .foregroundStyle(BrightPulse.inkMuted)
            if let url = URL(string: post.url) {
                Link("Open the original", destination: url)
                    .font(BrightPulseFont.body(size: 14, weight: .semibold))
                    .foregroundStyle(BrightPulse.coralInk)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(BrightPulse.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private enum MediaItem: Identifiable {
    case video(URL)
    case image(URL)

    var id: String {
        switch self {
        case .video(let url), .image(let url): return url.absoluteString
        }
    }
}

private struct Carousel: View {
    let items: [MediaItem]
    @State private var index = 0

    var body: some View {
        VStack(spacing: 8) {
            TabView(selection: $index) {
                ForEach(Array(items.enumerated()), id: \.offset) { offset, item in
                    itemView(item)
                        .tag(offset)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: items.count > 1 ? .always : .never))
            .aspectRatio(9.0 / 16.0, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            if items.count > 1 {
                Text("\(index + 1) / \(items.count)")
                    .font(BrightPulseFont.body(size: 12, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
    }

    @ViewBuilder
    private func itemView(_ item: MediaItem) -> some View {
        switch item {
        case .video(let url):
            VideoPageView(url: url)
        case .image(let url):
            AsyncImage(url: url) { phase in
                if case .success(let image) = phase {
                    image.resizable().aspectRatio(contentMode: .fit)
                } else {
                    Rectangle().fill(BrightPulse.surface2)
                }
            }
        }
    }
}

/// Owns a single `AVPlayer` instance for its URL and autoplays once the page
/// becomes visible (the user already navigated into Post Detail to watch
/// this, unlike a passive feed scroll, so playing with sound rather than a
/// muted preview matches intent) — the previous implementation constructed a
/// fresh `AVPlayer` directly inside `itemView`'s body, which SwiftUI
/// re-evaluates on every re-render, so playback kept getting reset before it
/// could ever establish and the video appeared frozen/unplayable. Pauses
/// when swiped away from.
private struct VideoPageView: View {
    let url: URL
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
            } else {
                Rectangle().fill(Color.black)
            }
        }
        .onAppear {
            let player = self.player ?? AVPlayer(url: url)
            self.player = player
            player.play()
        }
        .onDisappear {
            player?.pause()
        }
    }
}
