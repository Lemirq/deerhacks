import Foundation

struct CoachingEvent: Codable {
    let event: String
    let score: Double
    let message: String
    let detail: String
    let buzz: Bool
    let buzzPattern: String
    let confidence: Double
    let timestamp: Double
    let phase: String
    let reasoning: String

    enum CodingKeys: String, CodingKey {
        case event, score, message, detail, buzz
        case buzzPattern = "buzz_pattern"
        case confidence, timestamp, phase, reasoning
    }
}
