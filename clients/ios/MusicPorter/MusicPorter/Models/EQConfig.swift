import Foundation

/// Equalizer configuration with four independent audio effects.
struct EQConfig: Codable, Hashable {
    var loudnorm: Bool = false
    var bassBoost: Bool = false
    var trebleBoost: Bool = false
    var compressor: Bool = false

    var anyEnabled: Bool {
        loudnorm || bassBoost || trebleBoost || compressor
    }

    /// Convert to dictionary for inclusion in API request bodies.
    func toDict() -> [String: Any]? {
        guard anyEnabled else { return nil }
        var dict: [String: Any] = [:]
        if loudnorm { dict["loudnorm"] = true }
        if bassBoost { dict["bass_boost"] = true }
        if trebleBoost { dict["treble_boost"] = true }
        if compressor { dict["compressor"] = true }
        return dict
    }

    enum CodingKeys: String, CodingKey {
        case loudnorm
        case bassBoost = "bass_boost"
        case trebleBoost = "treble_boost"
        case compressor
    }
}

/// Response from GET /api/eq/resolve.
struct EQResolveResponse: Codable {
    let profile: String
    let playlist: String?
    let source: String
    let eq: EQConfig
    let filterChain: String?

    enum CodingKeys: String, CodingKey {
        case profile, playlist, source, eq
        case filterChain = "filter_chain"
    }
}

/// Response from GET /api/eq/effects.
struct EQEffectInfo: Codable, Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let filter: String
}
