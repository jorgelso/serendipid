import Foundation
import SerendipidCore

/// Shared by `ReviewActionsView`'s "Re-run analysis" and `MediaViewer`'s
/// "Re-fetch video" — both are the same `POST /analyze` with `force: true`,
/// mirroring the web app's `ReanalyzeButton`.
enum ReanalyzeService {
    struct Outcome {
        let success: Bool
        let message: String
    }

    static func reanalyze(url: String, apiClient: APIClient) async -> Outcome {
        do {
            let response: AnalysisResponse = try await apiClient.send(.analyze, body: AnalyzeRequest(url: url, force: true))
            if response.success {
                return Outcome(success: true, message: "Re-analyzed — refresh to see the update.")
            }
            return Outcome(success: false, message: response.error ?? "Reanalysis failed.")
        } catch let error as APIError {
            switch error {
            case .alreadyProcessing:
                return Outcome(success: false, message: "This post is already being analyzed. Please wait and try again.")
            case .serviceUnavailable:
                return Outcome(success: false, message: "The server is busy analyzing another post — try again shortly.")
            case .timeout:
                return Outcome(success: false, message: "Analysis timed out.")
            case .quotaQueuedForRetry(let message):
                return Outcome(success: false, message: message)
            default:
                return Outcome(success: false, message: error.errorDescription ?? "Reanalysis failed.")
            }
        } catch {
            return Outcome(success: false, message: error.localizedDescription)
        }
    }
}
