import Foundation

/// Mirrors `GET /categories`'s response.
public struct CategoriesResponse: Codable, Sendable {
    public let success: Bool
    public let categories: [CategoryCount]
    /// Full canonical taxonomy (`backend/core/categories.py`), independent of
    /// which categories currently have posts.
    public let canonical: [String]
    public let total: Int
}

public struct CategoryCount: Codable, Identifiable, Hashable, Sendable {
    public var id: String { self.categoryId }
    public let categoryId: String
    public let name: String
    public let count: Int

    enum CodingKeys: String, CodingKey {
        case categoryId = "id"
        case name, count
    }
}
