import SwiftUI

/// A row displaying a single track with artwork.
struct TrackRow: View {
    let track: Track
    let playlist: String
    let api: APIClient
    var isNowPlaying: Bool = false

    var body: some View {
        HStack(spacing: 12) {
            // Artwork thumbnail or now-playing indicator
            if isNowPlaying {
                Image(systemName: "speaker.wave.2.fill")
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 44, height: 44)
            } else if track.hasCoverArt == true, let url = api.artworkURL(playlist: playlist, filename: track.filename) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(contentMode: .fill)
                } placeholder: {
                    Image(systemName: "music.note")
                        .foregroundStyle(.secondary)
                }
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
                if let artist = track.artist {
                    Text(artist)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            // File size
            Text(ByteCountFormatter.string(fromByteCount: Int64(track.size), countStyle: .file))
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}
