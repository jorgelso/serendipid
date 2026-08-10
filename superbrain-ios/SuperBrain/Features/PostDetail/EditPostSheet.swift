import SwiftUI
import SuperBrainCore

/// Title/summary/category/language edit form — `PUT /post/{shortcode}`,
/// mirroring the web app's `EditPostForm`. Only the 4 keys the backend
/// honors are ever sent.
struct EditPostSheet: View {
    let post: Post
    let onSaved: () async -> Void

    @Environment(\.apiClient) private var apiClient
    @Environment(\.dismiss) private var dismiss

    @State private var title: String
    @State private var summary: String
    @State private var categories: [String]
    @State private var languages: [String]
    @State private var newCategory = ""
    @State private var newLanguage = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    init(post: Post, onSaved: @escaping () async -> Void) {
        self.post = post
        self.onSaved = onSaved
        _title = State(initialValue: post.title ?? "")
        _summary = State(initialValue: post.summary ?? "")
        _categories = State(initialValue: post.category)
        _languages = State(initialValue: post.language)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Title") {
                    TextField("Title", text: $title)
                }
                Section("Summary") {
                    TextEditor(text: $summary)
                        .frame(minHeight: 120)
                }
                Section("Category") {
                    chipEditor(items: $categories, newText: $newCategory, placeholder: "Add category")
                }
                Section("Language") {
                    chipEditor(items: $languages, newText: $newLanguage, placeholder: "Add language")
                }
                if let errorMessage {
                    Text(errorMessage).foregroundStyle(BrightPulse.danger)
                }
            }
            .navigationTitle("Edit post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isSaving ? "Saving…" : "Save") {
                        Task { await save() }
                    }
                    .disabled(isSaving)
                }
            }
        }
    }

    private func chipEditor(items: Binding<[String]>, newText: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            FlowLayout(spacing: 6) {
                ForEach(items.wrappedValue, id: \.self) { item in
                    HStack(spacing: 4) {
                        Text(item)
                        Button {
                            items.wrappedValue.removeAll { $0 == item }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                        }
                    }
                    .font(BrightPulseFont.body(size: 12, weight: .semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Capsule().fill(BrightPulse.surface2))
                }
            }
            HStack {
                TextField(placeholder, text: newText)
                Button("Add") {
                    let trimmed = newText.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty, !items.wrappedValue.contains(trimmed) else { return }
                    items.wrappedValue.append(trimmed)
                    newText.wrappedValue = ""
                }
            }
        }
    }

    private func save() async {
        isSaving = true
        errorMessage = nil
        do {
            let _: PostUpdateResponse = try await apiClient.send(
                .postUpdate(shortcode: post.shortcode),
                body: PostUpdateRequest(category: categories, language: languages, title: title, summary: summary)
            )
            await onSaved()
            dismiss()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isSaving = false
    }
}
