import Foundation
import UIKit

struct HealthResponse: Codable {
    let status: String
    let geminiKey: String
    let sessions: Int

    enum CodingKeys: String, CodingKey {
        case status
        case geminiKey = "gemini_key"
        case sessions
    }
}

class NetworkService {
    static var deviceId: String {
        UIDevice.current.identifierForVendor?.uuidString ?? "unknown"
    }

    func healthCheck(baseURL: String) async throws -> HealthResponse {
        guard let url = URL(string: "\(baseURL)/health") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(HealthResponse.self, from: data)
    }

    func analyze(baseURL: String, frame: Data, audioClip: Data, audioMetrics: AudioMetrics, sessionId: String) async throws -> CoachingEvent {
        let boundary = "----NeuroSync\(UUID().uuidString)"
        guard let url = URL(string: "\(baseURL)/analyze") else { throw URLError(.badURL) }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()

        // frame
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"frame\"; filename=\"frame.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(frame)
        body.append("\r\n".data(using: .utf8)!)

        // audio_clip
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio_clip\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioClip)
        body.append("\r\n".data(using: .utf8)!)

        // audio_metrics (JSON string as form field)
        let metricsJSON = try JSONEncoder().encode(audioMetrics)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio_metrics\"\r\n\r\n".data(using: .utf8)!)
        body.append(metricsJSON)
        body.append("\r\n".data(using: .utf8)!)

        // session_id
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"session_id\"\r\n\r\n".data(using: .utf8)!)
        body.append(sessionId.data(using: .utf8)!)
        body.append("\r\n".data(using: .utf8)!)

        // device_id
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"device_id\"\r\n\r\n".data(using: .utf8)!)
        body.append(NetworkService.deviceId.data(using: .utf8)!)
        body.append("\r\n".data(using: .utf8)!)

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(CoachingEvent.self, from: data)
    }

    func resetSession(baseURL: String, sessionId: String) async throws {
        guard let url = URL(string: "\(baseURL)/session/\(sessionId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.timeoutInterval = 5
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    func fetchReport(baseURL: String, sessionId: String) async throws -> SessionReport {
        guard let url = URL(string: "\(baseURL)/session/\(sessionId)/report?device_id=\(NetworkService.deviceId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(SessionReport.self, from: data)
    }

    func fetchReportHistory(baseURL: String) async throws -> [ReportSummary] {
        guard let url = URL(string: "\(baseURL)/reports/\(NetworkService.deviceId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode([ReportSummary].self, from: data)
    }

    func fetchSavedReport(baseURL: String, sessionId: String) async throws -> SessionReport {
        guard let url = URL(string: "\(baseURL)/reports/\(NetworkService.deviceId)/\(sessionId)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(SessionReport.self, from: data)
    }
}
