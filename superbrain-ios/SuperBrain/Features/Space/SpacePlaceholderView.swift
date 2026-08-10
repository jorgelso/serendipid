import SwiftUI
import SuperBrainCore

/// Placeholder only — the real 3D vector-space view (points plotted by
/// embedding similarity, colored by theme, RealityKit/SceneKit-based) is
/// deliberately out of scope for this build. It's a self-contained follow-up
/// with its own narrow brief (the `VectorSpacePoint` shape, the 8-hue
/// categorical palette, and the `DeepLink` interaction), kept separate so
/// that work isn't done with this whole app's context loaded — see the
/// implementation plan's Space section for what that brief should contain.
struct SpacePlaceholderView: View {
    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Image(systemName: "circle.hexagongrid")
                    .font(.system(size: 40))
                    .foregroundStyle(BrightPulse.inkMuted)
                Text("Space")
                    .font(BrightPulseFont.display(size: 20, weight: .semibold))
                    .foregroundStyle(BrightPulse.ink)
                Text("A 3D view of your saved posts, laid out by how similar they are — coming soon.")
                    .font(BrightPulseFont.body(size: 14))
                    .foregroundStyle(BrightPulse.inkMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(BrightPulse.background)
            .navigationTitle("Space")
        }
    }
}
