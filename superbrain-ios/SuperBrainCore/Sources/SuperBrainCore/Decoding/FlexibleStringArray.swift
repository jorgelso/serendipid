import Foundation

/// Decodes a field that the backend sometimes sends as `[String]` and sometimes
/// as a bare `String` (or omits/nulls) — e.g. `ChatSource.category`, which is
/// typed `string[] | string` even in the web frontend's own TypeScript types.
///
/// Only use this where the backend is genuinely inconsistent. `Post.category`,
/// `Post.language`, and `Post.tags` are guaranteed real arrays server-side and
/// should stay plain `[String]` — a decode failure there is a signal worth
/// surfacing, not silently patching over.
@propertyWrapper
public struct FlexibleStringArray: Codable, Hashable, Sendable {
    public var wrappedValue: [String]

    public init(wrappedValue: [String]) {
        self.wrappedValue = wrappedValue
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let array = try? container.decode([String].self) {
            wrappedValue = array
        } else if let single = try? container.decode(String.self) {
            // Some responses double-encode: the column is JSON-text-encoded
            // server-side and, in at least one observed case (`/export`'s
            // embedded `collections[].post_ids`, unlike the standalone
            // `/collections` endpoint which decodes it), that encoding isn't
            // unwrapped before being placed in the outer JSON — so the value
            // arrives as the *string* `"[\"a\", \"b\"]"` rather than a real
            // array. Try parsing it as nested JSON first; otherwise treat a
            // non-empty string as a genuine single value (e.g. `ChatSource
            // .category` sent as a bare string).
            if let nestedData = single.data(using: .utf8),
               let nested = try? JSONDecoder().decode([String].self, from: nestedData) {
                wrappedValue = nested
            } else {
                wrappedValue = single.isEmpty ? [] : [single]
            }
        } else {
            wrappedValue = []
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(wrappedValue)
    }
}

extension KeyedDecodingContainer {
    public func decode(
        _ type: FlexibleStringArray.Type,
        forKey key: Key
    ) throws -> FlexibleStringArray {
        if let value = try decodeIfPresent(FlexibleStringArray.self, forKey: key) {
            return value
        }
        return FlexibleStringArray(wrappedValue: [])
    }
}
