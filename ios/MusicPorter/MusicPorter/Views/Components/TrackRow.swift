import SwiftUI

/// A row displaying a single track with artwork.
struct TrackRow: View {
    let track: Track
    let playlist: String
    let api: APIClient

    var body: some View {
        HStack(spacing: 12) {
            // Artwork thumbnail
            if track.hasCoverArt == true, let url = api.artworkURL(playlist: playlist, filename: track.filename) {
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
