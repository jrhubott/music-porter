import Foundation

/// A playlist directory in the export folder with file count.
struct ExportDirectory: Identifiable, Codable, Hashable {
    var id: String { name }
    let name: String
    let displayName: String
    let files: Int

    enum CodingKeys: String, CodingKey {
        case name, files
        case displayName = "display_name"
    }
}
