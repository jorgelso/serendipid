import SwiftUI

/// Renders a post's thumbnail regardless of whether the backend sent a
/// remote URL or an inline `data:image/...;base64,...` URI — the inline case
/// decodes synchronously (already-local bytes, no network round-trip needed
/// the way `AsyncImage` would imply).
public struct ResolvedThumbnailImage: View {
    private let source: ThumbnailSource

    public init(raw: String?, baseURL: URL?) {
        self.source = MediaResolver.resolveThumbnail(raw, baseURL: baseURL)
    }

    public var body: some View {
        switch source {
        case .remoteURL(let url):
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().aspectRatio(contentMode: .fill)
                case .failure:
                    placeholder
                case .empty:
                    placeholder.overlay(ProgressView())
                @unknown default:
                    placeholder
                }
            }
        case .inlineData(let data):
            if let uiImage = PlatformImage(data: data) {
                uiImage.swiftUIImage.resizable().aspectRatio(contentMode: .fill)
            } else {
                placeholder
            }
        case .none:
            placeholder
        }
    }

    private var placeholder: some View {
        Rectangle().fill(BrightPulse.surface2)
    }
}

#if canImport(UIKit)
import UIKit
private struct PlatformImage {
    let uiImage: UIImage
    init?(data: Data) {
        guard let image = UIImage(data: data) else { return nil }
        self.uiImage = image
    }
    var swiftUIImage: Image { Image(uiImage: uiImage) }
}
#else
private struct PlatformImage {
    init?(data: Data) { return nil }
    var swiftUIImage: Image { Image(systemName: "photo") }
}
#endif
