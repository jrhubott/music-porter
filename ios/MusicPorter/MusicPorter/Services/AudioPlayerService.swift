import AVFoundation
import MediaPlayer
import MusicKit
import UIKit

/// Dual-engine audio player for server MP3s (AVPlayer) and Apple Music tracks (ApplicationMusicPlayer).
@MainActor @Observable
final class AudioPlayerService {
    // MARK: - Types

    enum PlaybackSource {
        case serverTrack
        case appleMusic
        case none
    }

    struct NowPlayingInfo: Equatable {
        let title: String
        let artist: String?
        let artworkURL: URL?
        let duration: TimeInterval
        let source: PlaybackSource

        static func == (lhs: NowPlayingInfo, rhs: NowPlayingInfo) -> Bool {
            lhs.title == rhs.title && lhs.artist == rhs.artist && lhs.duration == rhs.duration && lhs.artworkURL == rhs.artworkURL
        }
    }

    // MARK: - Observable State

    var isPlaying = false
    var nowPlaying: NowPlayingInfo?
    var playbackProgress: Double = 0 // 0...1
    var currentTime: TimeInterval = 0
    var duration: TimeInterval = 0
    var artworkImage: UIImage?

    var hasCurrentTrack: Bool { nowPlaying != nil }

    /// ID of the currently playing server track (filename).
    var currentServerTrackID: String?

    /// ID of the currently playing Apple Music track.
    var currentAppleMusicTrackID: MusicItemID?

    // MARK: - Private State

    @ObservationIgnored private var apiClient: APIClient?
    @ObservationIgnored private var audioCacheManager: AudioCacheManager?
    @ObservationIgnored private var avPlayer: AVPlayer?
    @ObservationIgnored private var timeObserver: Any?
    @ObservationIgnored private var endObserver: NSObjectProtocol?

    @ObservationIgnored private var appleMusicPlayer = ApplicationMusicPlayer.shared
    @ObservationIgnored private var appleMusicPollingTask: Task<Void, Never>?

    /// Queue context for skip forward/backward.
    @ObservationIgnored private var serverQueue: [Track] = []
    @ObservationIgnored private var serverQueuePlaylist: String?
    @ObservationIgnored private var serverQueueIndex: Int = 0
    @ObservationIgnored private var serverQueueDownloadManager: FileDownloadManager?

    @ObservationIgnored private var appleMusicQueue: [MusicKit.Track] = []
    @ObservationIgnored private var appleMusicQueueIndex: Int = 0

    @ObservationIgnored private var isSeeking = false

    // MARK: - Configuration

    func configure(apiClient: APIClient, audioCacheManager: AudioCacheManager? = nil) {
        self.apiClient = apiClient
        self.audioCacheManager = audioCacheManager
        configureAudioSession()
        configureRemoteCommands()
    }

    // MARK: - Server Track Playback

    func playServerTrack(track: Track, in tracks: [Track], playlist: String, downloadManager: FileDownloadManager) {
        stopInternal()

        guard let apiClient else { return }
        self.serverQueueDownloadManager = downloadManager

        // Build queue
        serverQueue = tracks
        serverQueuePlaylist = playlist
        serverQueueIndex = tracks.firstIndex(where: { $0.filename == track.filename }) ?? 0

        // Priority 1: local file
        let localFiles = downloadManager.localFiles(playlist: playlist)
        if let localFile = localFiles.first(where: { $0.lastPathComponent == track.filename }) {
            let asset = AVURLAsset(url: localFile)
            beginPlayback(asset: asset, track: track, playlist: playlist)
            return
        }

        // Priority 2: cache — requires async check, then fall back to server stream
        let cacheManager = audioCacheManager
        let uuid = track.uuid

        Task {
            var cachedURL: URL?
            if let uuid, let cacheManager {
                cachedURL = await cacheManager.isCached(uuid)
            }

            if let cachedURL {
                let asset = AVURLAsset(url: cachedURL)
                beginPlayback(asset: asset, track: track, playlist: playlist)
            } else {
                // Priority 3: server stream
                guard let streamURL = apiClient.fileDownloadURL(playlist: playlist, filename: track.filename) else { return }
                let headers = ["Authorization": "Bearer \(apiClient.apiKey ?? "")"]
                let asset = AVURLAsset(url: streamURL, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
                beginPlayback(asset: asset, track: track, playlist: playlist)
            }
        }
    }

    /// Start playback with a resolved asset.
    private func beginPlayback(asset: AVURLAsset, track: Track, playlist: String) {
        let item = AVPlayerItem(asset: asset)
        let player = AVPlayer(playerItem: item)
        self.avPlayer = player

        // Artwork URL
        let artworkURL = apiClient?.artworkURL(playlist: playlist, filename: track.filename)

        nowPlaying = NowPlayingInfo(
            title: track.displayTitle,
            artist: track.artist,
            artworkURL: artworkURL,
            duration: track.duration ?? 0,
            source: .serverTrack
        )
        artworkImage = nil
        currentServerTrackID = track.filename
        currentAppleMusicTrackID = nil

        // Fetch artwork via authenticated API (AsyncImage can't send Bearer tokens)
        let artworkPlaylist = playlist
        let artworkFilename = track.filename
        Task {
            let cacheKey = "\(artworkPlaylist)/\(artworkFilename)"
            if let cached = ArtworkCache.shared.get(cacheKey) {
                self.artworkImage = cached
            } else if let image = await apiClient?.fetchArtwork(playlist: artworkPlaylist, filename: artworkFilename) {
                ArtworkCache.shared.set(cacheKey, image: image)
                self.artworkImage = image
            }
        }
        duration = track.duration ?? 0

        setupAVPlayerObservers(player: player)
        player.play()
        isPlaying = true
        updateNowPlayingInfoCenter()
    }

    // MARK: - Apple Music Playback

    func playAppleMusicTrack(track: MusicKit.Track, in tracks: [MusicKit.Track]) {
        stopInternal()

        appleMusicQueue = tracks
        appleMusicQueueIndex = tracks.firstIndex(where: { $0.id == track.id }) ?? 0

        // Build queue starting from the selected track
        let queueTracks = Array(tracks.suffix(from: appleMusicQueueIndex))
        appleMusicPlayer.queue = ApplicationMusicPlayer.Queue(for: queueTracks)

        nowPlaying = NowPlayingInfo(
            title: track.title,
            artist: track.artistName,
            artworkURL: track.artwork?.url(width: 100, height: 100),
            duration: track.duration ?? 0,
            source: .appleMusic
        )
        artworkImage = nil
        currentAppleMusicTrackID = track.id
        currentServerTrackID = nil
        duration = track.duration ?? 0

        Task {
            do {
                try await appleMusicPlayer.play()
                isPlaying = true
                startAppleMusicPolling()
            } catch {
                // Apple Music playback failed (no subscription, etc.)
                self.nowPlaying = nil
                self.isPlaying = false
            }
        }
    }

    // MARK: - Controls

    func togglePlayPause() {
        guard let nowPlaying else { return }
        switch nowPlaying.source {
        case .serverTrack:
            guard let player = avPlayer else { return }
            if isPlaying {
                player.pause()
            } else {
                player.play()
            }
            isPlaying.toggle()

        case .appleMusic:
            if isPlaying {
                appleMusicPlayer.pause()
            } else {
                Task { try? await appleMusicPlayer.play() }
            }
            isPlaying.toggle()

        case .none:
            break
        }
        updateNowPlayingInfoCenter()
    }

    func skipForward() {
        guard let nowPlaying else { return }
        switch nowPlaying.source {
        case .serverTrack:
            guard serverQueueIndex < serverQueue.count - 1,
                  let playlist = serverQueuePlaylist,
                  let dm = serverQueueDownloadManager else { return }
            serverQueueIndex += 1
            playServerTrack(track: serverQueue[serverQueueIndex], in: serverQueue, playlist: playlist, downloadManager: dm)

        case .appleMusic:
            guard appleMusicQueueIndex < appleMusicQueue.count - 1 else { return }
            appleMusicQueueIndex += 1
            playAppleMusicTrack(track: appleMusicQueue[appleMusicQueueIndex], in: appleMusicQueue)

        case .none:
            break
        }
    }

    func skipBackward() {
        guard let nowPlaying else { return }
        // If more than 3 seconds in, restart current track
        if currentTime > 3 {
            seek(to: 0)
            return
        }

        switch nowPlaying.source {
        case .serverTrack:
            guard serverQueueIndex > 0,
                  let playlist = serverQueuePlaylist,
                  let dm = serverQueueDownloadManager else { return }
            serverQueueIndex -= 1
            playServerTrack(track: serverQueue[serverQueueIndex], in: serverQueue, playlist: playlist, downloadManager: dm)

        case .appleMusic:
            guard appleMusicQueueIndex > 0 else { return }
            appleMusicQueueIndex -= 1
            playAppleMusicTrack(track: appleMusicQueue[appleMusicQueueIndex], in: appleMusicQueue)

        case .none:
            break
        }
    }

    func seek(to fraction: Double) {
        guard let nowPlaying else { return }
        let targetTime = duration * fraction

        switch nowPlaying.source {
        case .serverTrack:
            let cmTime = CMTime(seconds: targetTime, preferredTimescale: 600)
            avPlayer?.seek(to: cmTime, toleranceBefore: .zero, toleranceAfter: .zero)
            currentTime = targetTime
            playbackProgress = fraction

        case .appleMusic:
            appleMusicPlayer.playbackTime = targetTime
            currentTime = targetTime
            playbackProgress = fraction

        case .none:
            break
        }
        updateNowPlayingInfoCenter()
    }

    /// Called from MiniPlayerView when the user starts/stops dragging the slider.
    func setIsSeeking(_ seeking: Bool) {
        isSeeking = seeking
    }

    func stop() {
        stopInternal()
        nowPlaying = nil
        artworkImage = nil
        isPlaying = false
        playbackProgress = 0
        currentTime = 0
        duration = 0
        currentServerTrackID = nil
        currentAppleMusicTrackID = nil
        serverQueue = []
        appleMusicQueue = []
        clearNowPlayingInfoCenter()
    }

    // MARK: - Audio Session

    private func configureAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default)
            try session.setActive(true)
        } catch {
            // Audio session configuration failed — playback may not work in background
        }
    }

    // MARK: - AVPlayer Observers

    private func setupAVPlayerObservers(player: AVPlayer) {
        // Periodic time observer (every 0.5s)
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            Task { @MainActor in
                guard let self, !self.isSeeking else { return }
                self.currentTime = time.seconds
                if let item = player.currentItem {
                    let dur = item.duration.seconds
                    if dur.isFinite && dur > 0 {
                        self.duration = dur
                        self.playbackProgress = time.seconds / dur
                        self.updateNowPlayingInfoCenter()
                    }
                }
            }
        }

        // End-of-track notification
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: player.currentItem,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleTrackEnd()
            }
        }
    }

    private func handleTrackEnd() {
        // Auto-advance to next track in queue
        guard let nowPlaying else { return }
        switch nowPlaying.source {
        case .serverTrack:
            if serverQueueIndex < serverQueue.count - 1 {
                skipForward()
            } else {
                stop()
            }
        case .appleMusic:
            // ApplicationMusicPlayer handles queue advancement itself
            break
        case .none:
            break
        }
    }

    // MARK: - Apple Music Polling

    private func startAppleMusicPolling() {
        appleMusicPollingTask?.cancel()
        appleMusicPollingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(500))
                guard !Task.isCancelled else { break }
                self?.pollAppleMusicState()
            }
        }
    }

    private func pollAppleMusicState() {
        guard nowPlaying?.source == .appleMusic, !isSeeking else { return }

        let state = appleMusicPlayer.state
        isPlaying = (state.playbackStatus == .playing)
        currentTime = appleMusicPlayer.playbackTime

        if duration > 0 {
            playbackProgress = currentTime / duration
        }
    }

    // MARK: - Now Playing Info Center

    private func configureRemoteCommands() {
        let center = MPRemoteCommandCenter.shared()

        center.playCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlayPause() }
            return .success
        }
        center.pauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlayPause() }
            return .success
        }
        center.togglePlayPauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlayPause() }
            return .success
        }
        center.nextTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.skipForward() }
            return .success
        }
        center.previousTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.skipBackward() }
            return .success
        }
        center.changePlaybackPositionCommand.addTarget { [weak self] event in
            guard let posEvent = event as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            let fraction = posEvent.positionTime / (self?.duration ?? 1)
            Task { @MainActor in self?.seek(to: fraction) }
            return .success
        }
    }

    private func updateNowPlayingInfoCenter() {
        guard let nowPlaying else { return }
        var info = [String: Any]()
        info[MPMediaItemPropertyTitle] = nowPlaying.title
        info[MPMediaItemPropertyArtist] = nowPlaying.artist ?? ""
        info[MPMediaItemPropertyPlaybackDuration] = duration
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = currentTime
        info[MPNowPlayingInfoPropertyPlaybackRate] = isPlaying ? 1.0 : 0.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func clearNowPlayingInfoCenter() {
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }

    // MARK: - Internal Cleanup

    private func stopInternal() {
        // Stop AVPlayer
        if let observer = timeObserver, let player = avPlayer {
            player.removeTimeObserver(observer)
        }
        timeObserver = nil
        if let endObs = endObserver {
            NotificationCenter.default.removeObserver(endObs)
        }
        endObserver = nil
        avPlayer?.pause()
        avPlayer = nil

        // Stop Apple Music polling
        appleMusicPollingTask?.cancel()
        appleMusicPollingTask = nil
    }
}
