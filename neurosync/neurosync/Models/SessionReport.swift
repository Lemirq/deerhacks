import Foundation

struct SessionReport: Codable {
    let sessionId: String
    let hookEvaluation: HookEvaluation?
    let stats: SessionStats
    let bestMoment: ReportMoment?
    let worstMoment: ReportMoment?
    let problemZones: [ProblemZone]
    let timeline: [TimelineEvent]

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case hookEvaluation = "hook_evaluation"
        case stats
        case bestMoment = "best_moment"
        case worstMoment = "worst_moment"
        case problemZones = "problem_zones"
        case timeline
    }
}

struct HookEvaluation: Codable {
    let verdict: String
    let avgScore: Double
    let evaluations: [CoachingEvent]

    enum CodingKeys: String, CodingKey {
        case verdict
        case avgScore = "avg_score"
        case evaluations
    }
}

struct SessionStats: Codable {
    let totalEvents: Int
    let avgScore: Double
    let minScore: Double
    let maxScore: Double
    let eventCounts: [String: Int]

    enum CodingKeys: String, CodingKey {
        case totalEvents = "total_events"
        case avgScore = "avg_score"
        case minScore = "min_score"
        case maxScore = "max_score"
        case eventCounts = "event_counts"
    }
}

struct ReportMoment: Codable {
    let frameIndex: Int
    let score: Double
    let event: String
    let message: String
    let reasoning: String

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case score, event, message, reasoning
    }
}

struct ProblemZone: Codable {
    let startFrame: Int
    let endFrame: Int
    let avgScore: Double
    let dominantEvent: String

    enum CodingKeys: String, CodingKey {
        case startFrame = "start_frame"
        case endFrame = "end_frame"
        case avgScore = "avg_score"
        case dominantEvent = "dominant_event"
    }
}

struct TimelineEvent: Codable {
    let frameIndex: Int
    let event: String
    let score: Double
    let message: String

    enum CodingKeys: String, CodingKey {
        case frameIndex = "frame_index"
        case event, score, message
    }
}

struct ReportSummary: Codable, Identifiable {
    let sessionId: String
    let timestamp: Double
    let avgScore: Double
    let hookVerdict: String?
    let totalEvents: Int

    var id: String { sessionId }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case timestamp
        case avgScore = "avg_score"
        case hookVerdict = "hook_verdict"
        case totalEvents = "total_events"
    }
}
