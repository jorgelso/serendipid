import SwiftUI
import SuperBrainCore

struct BrowseFiltersView: View {
    let categories: [String]
    let languages: [String]
    let collections: [PostCollection]

    @Binding var selectedCategory: String?
    @Binding var selectedLanguage: String?
    @Binding var selectedCollectionID: String?
    @Binding var selectedEloquenceFilter: BrowseViewModel.EloquenceFilter?
    @Binding var sortOrder: BrowseViewModel.SortOrder
    let onClear: () -> Void

    private var hasActiveFilter: Bool {
        selectedCategory != nil || selectedLanguage != nil || selectedCollectionID != nil || selectedEloquenceFilter != nil
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                sortMenu
                filterMenu(title: "Category", selection: $selectedCategory, options: categories)
                filterMenu(title: "Language", selection: $selectedLanguage, options: languages)
                collectionMenu
                eloquenceMenu

                if hasActiveFilter {
                    Button("Clear", action: onClear)
                        .font(BrightPulseFont.body(size: 13, weight: .semibold))
                        .foregroundStyle(BrightPulse.coralInk)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
    }

    private var sortMenu: some View {
        Menu {
            ForEach(BrowseViewModel.SortOrder.allCases, id: \.self) { order in
                Button(order.rawValue) { sortOrder = order }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "arrow.up.arrow.down")
                    .font(.system(size: 10, weight: .semibold))
                Text(sortOrder.rawValue)
            }
            .font(BrightPulseFont.body(size: 13, weight: .semibold))
            .foregroundStyle(BrightPulse.ink)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Capsule().fill(BrightPulse.surface2))
        }
    }

    private var eloquenceMenu: some View {
        Menu {
            Button("All") { selectedEloquenceFilter = nil }
            ForEach(BrowseViewModel.EloquenceFilter.allCases, id: \.self) { filter in
                Button(filter.rawValue) { selectedEloquenceFilter = filter }
            }
        } label: {
            filterLabel(title: "Delivery", value: selectedEloquenceFilter?.rawValue)
        }
    }

    private func filterMenu(title: String, selection: Binding<String?>, options: [String]) -> some View {
        Menu {
            Button("All") { selection.wrappedValue = nil }
            ForEach(options, id: \.self) { option in
                Button(option) { selection.wrappedValue = option }
            }
        } label: {
            filterLabel(title: title, value: selection.wrappedValue)
        }
    }

    private var collectionMenu: some View {
        Menu {
            Button("All") { selectedCollectionID = nil }
            ForEach(collections) { collection in
                Button(collection.name) { selectedCollectionID = collection.id }
            }
        } label: {
            filterLabel(title: "Collection", value: collections.first { $0.id == selectedCollectionID }?.name)
        }
    }

    private func filterLabel(title: String, value: String?) -> some View {
        HStack(spacing: 4) {
            Text(value ?? title)
            Image(systemName: "chevron.down")
                .font(.system(size: 10, weight: .semibold))
        }
        .font(BrightPulseFont.body(size: 13, weight: .semibold))
        .foregroundStyle(value == nil ? BrightPulse.inkMuted : BrightPulse.ink)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Capsule().fill(value == nil ? BrightPulse.surface2 : BrightPulse.coralSoft))
    }
}
