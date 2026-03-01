import Foundation

struct AudioMetrics: Codable {
    let volumeRms: Double
    let silenceRatio: Double
    let estimatedWpm: Int
    let peakVolume: Double
    let volumeVariance: Double

    enum CodingKeys: String, CodingKey {
        case volumeRms = "volume_rms"
        case silenceRatio = "silence_ratio"
        case estimatedWpm = "estimated_wpm"
        case peakVolume = "peak_volume"
        case volumeVariance = "volume_variance"
    }
}
