import SwiftUI
import SerendipidCore

/// Shown only when `post.needs_review` — "Re-run analysis" / "Keep as is",
/// ports the web app's `ReviewActions` idle/loading/success/error states.
struct ReviewActionsView: View {
    let post: Post
    let onReload: () async -> Void

    @Environment(\.apiClient) private var apiClient
    @State private var state: ActionState = .idle

    private enum ActionState: Equatable {
        case idle
        case reanalyzing
        case markingReviewed
        case success(String)
        case failure(String)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Analyzed under an older version of the analysis pipeline.")
                .font(BrightPulseFont.body(size: 13, weight: .semibold))
                .foregroundStyle(BrightPulse.yellowInk)

            HStack(spacing: 10) {
                PillButton(
                    state == .reanalyzing ? "Re-analyzing… (can take a few minutes)" : "Re-run analysis",
                    isLoading: state == .reanalyzing
                ) {
                    Task { await reanalyze() }
                }
                PillButton(
                    state == .markingReviewed ? "Marking…" : "Keep as is",
                    style: .secondary,
                    isLoading: state == .markingReviewed
                ) {
                    Task { await markReviewed() }
                }
            }

            switch state {
            case .success(let message):
                HStack(spacing: 6) {
                    Text(message)
                    Button("Refresh") {
                        Task { await onReload() }
                    }
                    .foregroundStyle(BrightPulse.coralInk)
                }
                .font(BrightPulseFont.body(size: 13))
            case .failure(let message):
                Text(message)
                    .font(BrightPulseFont.body(size: 13))
                    .foregroundStyle(BrightPulse.danger)
            case .idle, .reanalyzing, .markingReviewed:
                EmptyView()
            }
        }
        .padding(16)
        .background(BrightPulse.yellowSoft)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func reanalyze() async {
        state = .reanalyzing
        let outcome = await ReanalyzeService.reanalyze(url: post.url, apiClient: apiClient)
        state = outcome.success ? .success(outcome.message) : .failure(outcome.message)
    }

    private func markReviewed() async {
        state = .markingReviewed
        do {
            let _: PostUpdateResponse = try await apiClient.send(
                .postUpdate(shortcode: post.shortcode),
                body: PostUpdateRequest(reviewed: true)
            )
            state = .success("Marked reviewed.")
        } catch {
            state = .failure((error as? APIError)?.errorDescription ?? error.localizedDescription)
        }
    }
}
