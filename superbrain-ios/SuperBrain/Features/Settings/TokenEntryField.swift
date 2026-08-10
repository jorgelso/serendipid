import SwiftUI
import SuperBrainCore

/// 8-box segmented token entry — mirrors the Android app's Settings screen
/// UX. Implemented as a hidden `TextField` overlaying 8 visual boxes (the
/// standard SwiftUI OTP-field trick) rather than 8 real `TextField`s with
/// manual focus-advancing, which is far more fragile to get right (paste,
/// backspace-across-boxes, autofill).
struct TokenEntryField: View {
    @Binding var token: String
    @FocusState private var isFocused: Bool

    var body: some View {
        ZStack {
            HStack(spacing: 8) {
                ForEach(0..<AccessToken.length, id: \.self) { index in
                    boxView(for: index)
                }
            }

            TextField("", text: $token)
                .keyboardType(.asciiCapable)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .focused($isFocused)
                .opacity(0.01)
                .onChange(of: token) { _, newValue in
                    let normalized = AccessToken.normalize(newValue)
                    token = String(normalized.prefix(AccessToken.length))
                }
        }
        .onTapGesture { isFocused = true }
    }

    private func boxView(for index: Int) -> some View {
        let characters = Array(token)
        let character = index < characters.count ? String(characters[index]) : ""
        let isActive = index == characters.count && isFocused

        return Text(character)
            .font(BrightPulseFont.display(size: 20, weight: .semibold))
            .foregroundStyle(BrightPulse.ink)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(BrightPulse.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(isActive ? BrightPulse.coral : BrightPulse.line, lineWidth: isActive ? 2 : 1)
            )
    }
}

#Preview {
    TokenEntryField(token: .constant("AB12"))
        .padding()
}
