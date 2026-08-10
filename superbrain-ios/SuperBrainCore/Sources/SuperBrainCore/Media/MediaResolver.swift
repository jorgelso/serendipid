import Foundation

/// Where a post's thumbnail actually lives — ports `superbrain-web/src/lib/posts.ts`'s
/// thumbnail resolution. `Post.thumbnail` is never guaranteed to be a loadable
/// URL: it can be a normal http(s) URL, a `/static/...` relative path, or a
/// full `data:image/...;base64,...` data URI saved directly by the analysis
/// pipeline — all three are real, observed shapes, not hypotheticals.
public enum ThumbnailSource: Equatable, Sendable {
    case remoteURL(URL)
    case inlineData(Data)
    case none
}

public enum MediaResolver {
    public static func resolveThumbnail(_ raw: String?, baseURL: URL?) -> ThumbnailSource {
        guard let raw, !raw.isEmpty else { return .none }

        if raw.hasPrefix("data:image/") {
            guard let commaIndex = raw.firstIndex(of: ","),
                  let data = Data(base64Encoded: String(raw[raw.index(after: commaIndex)...]))
            else {
                return .none
            }
            return .inlineData(data)
        }

        if raw.hasPrefix("http://") || raw.hasPrefix("https://") {
            return URL(string: raw).map(ThumbnailSource.remoteURL) ?? .none
        }

        if raw.hasPrefix("/"), let baseURL {
            return URL(string: raw, relativeTo: baseURL).map(ThumbnailSource.remoteURL) ?? .none
        }

        return .none
    }

    /// `Post.media_urls` entries are relative ("/media/{shortcode}/...") —
    /// the `/media` mount has no auth dependency, same as `/static`.
    public static func resolveMediaURLs(_ mediaURLs: [String], baseURL: URL) -> [URL] {
        mediaURLs.compactMap { path in
            if path.hasPrefix("http://") || path.hasPrefix("https://") {
                return URL(string: path)
            }
            return URL(string: path, relativeTo: baseURL)
        }
    }

    private static let videoExtensions: Set<String> = ["mp4", "mov", "m4v"]
    private static let imageExtensions: Set<String> = ["jpg", "jpeg", "png", "webp", "gif"]

    public struct ClassifiedMedia: Sendable {
        public let videos: [URL]
        public let images: [URL]

        public init(videos: [URL], images: [URL]) {
            self.videos = videos
            self.images = images
        }
    }

    /// Splits resolved media URLs into video/image buckets, sorted by the
    /// leading number in each filename ("2.jpg" before "10.jpg") rather than
    /// lexicographically — carousels are named "1.mp4", "2.jpg", etc.
    public static func classifyMedia(_ urls: [URL]) -> ClassifiedMedia {
        let sorted = urls.sorted { naturalSortKey($0) < naturalSortKey($1) }
        var videos: [URL] = []
        var images: [URL] = []
        for url in sorted {
            let ext = url.pathExtension.lowercased()
            if videoExtensions.contains(ext) {
                videos.append(url)
            } else if imageExtensions.contains(ext) {
                images.append(url)
            }
        }
        return ClassifiedMedia(videos: videos, images: images)
    }

    private static func naturalSortKey(_ url: URL) -> Int {
        let filename = url.deletingPathExtension().lastPathComponent
        let leadingDigits = filename.prefix { $0.isNumber }
        return Int(leadingDigits) ?? Int.max
    }

    /// True only for Instagram posts with no downloaded video file — the
    /// "needs re-fetch" condition (independent of `needs_review`), mirroring
    /// `superbrain-web/src/lib/media.ts`'s `isMissingVideo`.
    public static func isMissingVideo(_ post: Post) -> Bool {
        guard post.content_type == "instagram" else { return false }
        return !post.media_files.contains { videoExtensions.contains(URL(fileURLWithPath: $0).pathExtension.lowercased()) }
    }
}
