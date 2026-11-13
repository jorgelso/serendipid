import SwiftUI
import SerendipidCore

/// Horizontal bar list — ports the web app's `StatBars` exactly: bar width
/// relative to the max count (6% floor so small values stay visible), colored
/// via the same `colorFor(label)` hash used for tag/category pills, count
/// shown inside the bar.
struct StatBarsView: View {
    let entries: [(label: String, count: Int)]

    var body: some View {
        if entries.isEmpty {
            Text("Nothing to show yet.")
                .font(BrightPulseFont.body(size: 13))
                .foregroundStyle(BrightPulse.inkMuted)
        } else {
            let maxCount = entries.map(\.count).max() ?? 1
            VStack(alignment: .leading, spacing: 8) {
                ForEach(entries, id: \.label) { entry in
                    row(entry: entry, maxCount: maxCount)
                }
            }
        }
    }

    private func row(entry: (label: String, count: Int), maxCount: Int) -> some View {
        let fraction = max(Double(entry.count) / Double(maxCount), 0.06)
        let colors = BrightPulse.colorFor(entry.label)

        return VStack(alignment: .leading, spacing: 3) {
            Text(entry.label)
                .font(BrightPulseFont.body(size: 12, weight: .semibold))
                .foregroundStyle(BrightPulse.inkMuted)

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(BrightPulse.surface2)
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(colors.soft)
                        .frame(width: geometry.size.width * fraction)
                    Text("\(entry.count)")
                        .font(BrightPulseFont.body(size: 11, weight: .bold))
                        .foregroundStyle(colors.ink)
                        .padding(.leading, 8)
                }
            }
            .frame(height: 22)
        }
    }
}
