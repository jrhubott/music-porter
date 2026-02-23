import Foundation

/// A playlist directory in the export folder with file count.
struct ExportDirectory: Identifiable, Codable, Hashable {
    var id: String { name }
    let name: String
    let files: Int
}
