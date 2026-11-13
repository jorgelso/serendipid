import SwiftUI
import SerendipidCore

/// Two independent tri-state ratings — `nil → "liked" → "loved" → nil` —
/// distinct from the AI-scored `importance` badge. Ports the web app's
/// `RatingControls.tsx`; these are the user's own explicit-feedback signal
/// into `RecommendationsEngine`/the web recommendations engine, not an
/// AI judgment. `PUT /post/{shortcode}` only.
struct RatingControlsView: View {
    let post: Post
    let onSaved: () async -> Void

    @Environment(\.apiClient) private var apiClient
    @State private var enjoymentRating: String?
    @State private var importanceRating: String?
    @State private var isSaving = false

    init(post: Post, onSaved: @escaping () async -> Void) {
        self.post = post
        self.onSaved = onSaved
        _enjoymentRating = State(initialValue: post.enjoyment_rating)
        _importanceRating = State(initialValue: post.perceived_importance_rating)
    }

    var body: some View {
        HStack(spacing: 20) {
            ratingControl(symbol: "heart", label: "Enjoyed", rating: enjoymentRating) { next in
                Task { await update(enjoymentRating: next) }
            }
            ratingControl(symbol: "star", label: "Matters to me", rating: importanceRating) { next in
                Task { await update(importanceRating: next) }
            }
            if isSaving {
                ProgressView().scaleEffect(0.7)
            }
            Spacer()
        }
    }

    private func ratingControl(symbol: String, label: String, rating: String?, onTap: @escaping (String?) -> Void) -> some View {
        Button {
            onTap(Self.nextRating(after: rating))
        } label: {
            VStack(spacing: 4) {
                Image(systemName: iconName(symbol: symbol, rating: rating))
                    .font(.system(size: 18))
                    .foregroundStyle(color(for: rating))
                Text(label)
                    .font(BrightPulseFont.body(size: 10, weight: .semibold))
                    .foregroundStyle(BrightPulse.inkMuted)
            }
        }
        .buttonStyle(.plain)
        .disabled(isSaving)
    }

    private func iconName(symbol: String, rating: String?) -> String {
        switch rating {
        case "liked": return "\(symbol).fill"
        case "loved": return "\(symbol).fill"
        default: return symbol
        }
    }

    private func color(for rating: String?) -> Color {
        switch rating {
        case "loved": return BrightPulse.coral
        case "liked": return BrightPulse.yellowInk
        default: return BrightPulse.inkMuted
        }
    }

    /// Cycles `nil → liked → loved → nil` on repeated taps.
    private static func nextRating(after rating: String?) -> String? {
        switch rating {
        case nil: return "liked"
        case "liked": return "loved"
        default: return nil
        }
    }

    private func update(enjoymentRating next: String?) async {
        let previous = enjoymentRating
        enjoymentRating = next
        isSaving = true
        do {
            let _: PostUpdateResponse = try await apiClient.send(
                .postUpdate(shortcode: post.shortcode),
                body: PostUpdateRequest(enjoyment_rating: .some(next))
            )
            await onSaved()
        } catch {
            enjoymentRating = previous
        }
        isSaving = false
    }

    private func update(importanceRating next: String?) async {
        let previous = importanceRating
        importanceRating = next
        isSaving = true
        do {
            let _: PostUpdateResponse = try await apiClient.send(
                .postUpdate(shortcode: post.shortcode),
                body: PostUpdateRequest(perceived_importance_rating: .some(next))
            )
            await onSaved()
        } catch {
            importanceRating = previous
        }
        isSaving = false
    }
}
