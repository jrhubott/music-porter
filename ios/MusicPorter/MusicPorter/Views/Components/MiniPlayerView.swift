import SwiftUI

/// Compact player bar shown when a track is playing.
struct MiniPlayerView: View {
    @Environment(AppState.self) private var appState

    @State private var sliderValue: Double = 0
    @State private var isDragging = false

    private var audioPlayer: AudioPlayerService { appState.audioPlayer }

    var body: some View {
        VStack(spacing: 0) {
            Divider()

            VStack(spacing: 6) {
                // Track info + controls
                HStack(spacing: 12) {
                    artwork
                        .frame(width: 44, height: 44)
                        .clipShape(RoundedRectangle(cornerRadius: 6))

                    // Title / Artist
                    VStack(alignment: .leading, spacing: 2) {
                        Text(audioPlayer.nowPlaying?.title ?? "")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .lineLimit(1)

                        if let artist = audioPlayer.nowPlaying?.artist {
                            Text(artist)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }

                    Spacer()

                    // Controls
                    HStack(spacing: 20) {
                        Button { audioPlayer.skipBackward() } label: {
                            Image(systemName: "backward.fill")
                                .font(.body)
                        }

                        Button { audioPlayer.togglePlayPause() } label: {
                            Image(systemName: audioPlayer.isPlaying ? "pause.fill" : "play.fill")
                                .font(.title3)
                        }

                        Button { audioPlayer.skipForward() } label: {
                            Image(systemName: "forward.fill")
                                .font(.body)
                        }
                    }
                    .foregroundStyle(.primary)
                }
                .padding(.horizontal)

                // Seek slider
                Slider(
                    value: $sliderValue,
                    in: 0...1,
                    onEditingChanged: { editing in
                        isDragging = editing
                        audioPlayer.setIsSeeking(editing)
                        if !editing {
                            audioPlayer.seek(to: sliderValue)
                        }
                    }
                )
                .tint(.accentColor)
                .padding(.horizontal)
            }
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)
        }
        .onChange(of: audioPlayer.playbackProgress) { _, newValue in
            if !isDragging {
                sliderValue = newValue
            }
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    @ViewBuilder
    private var artwork: some View {
        if let url = audioPlayer.nowPlaying?.artworkURL {
            AsyncImage(url: url) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Image(systemName: "music.note")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(.systemGray5))
            }
        } else {
            Image(systemName: "music.note")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.systemGray5))
        }
    }
}
