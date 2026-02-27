import SwiftUI

/// In-memory artwork cache shared across all TrackRow instances.
private final class ArtworkCache {
    static let shared = ArtworkCache()
    private var cache: [String: UIImage] = [:]
    private let lock = NSLock()

    func get(_ key: String) -> UIImage? {
        lock.withLock { cache[key] }
    }

    func set(_ key: String, image: UIImage) {
        lock.withLock { cache[key] = image }
    }
}

/// A row displaying a single track with artwork.
struct TrackRow: View {
    let track: Track
    let playlist: String
    let api: APIClient
    var isNowPlaying: Bool = false
    var isLocal: Bool = false

    @State private var artwork: UIImage?

    private var cacheKey: String { "\(playlist)/\(track.filename)" }

    var body: some View {
        HStack(spacing: 12) {
            // Artwork thumbnail or now-playing indicator
            if isNowPlaying {
                Image(systemName: "speaker.wave.2.fill")
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 44, height: 44)
            } else if let artwork {
                Image(uiImage: artwork)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 44, height: 44)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                Image(systemName: "music.note")
                    .frame(width: 44, height: 44)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(track.displayTitle)
                    .font(.body)
                    .lineLimit(1)
                    .foregroundStyle(isNowPlaying ? Color.accentColor : .primary)
                HStack(spacing: 4) {
                    if let artist = track.artist {
                        Text(artist)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer()
                    Image(systemName: isLocal ? "iphone" : "cloud")
                        .font(.caption2)
                        .foregroundStyle(isLocal ? .green : .secondary)
                    Text(ByteCountFormatter.string(fromByteCount: Int64(track.size), countStyle: .file))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .frame(minWidth: 54, alignment: .trailing)
                }
            }
        }
        .task(id: cacheKey) {
            guard track.hasCoverArt == true else { return }
            if let cached = ArtworkCache.shared.get(cacheKey) {
                artwork = cached
                return
            }
            if let image = await api.fetchArtwork(playlist: playlist, filename: track.filename) {
                ArtworkCache.shared.set(cacheKey, image: image)
                artwork = image
            }
        }
    }
}
