import AVFoundation
import Combine

class AudioService: ObservableObject {
    private let engine = AVAudioEngine()
    private let lock = NSLock()
    private var buffer: [Float] = []
    private let sampleRate: Double = 16000
    private let windowSamples = 24000 // 1.5s at 16kHz

    func startCapture() {
        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        // Target format: 16kHz mono Float32
        guard let targetFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false) else { return }
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else { return }

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] pcmBuffer, _ in
            guard let self = self else { return }

            // Convert to 16kHz mono
            let ratio = sampleRate / inputFormat.sampleRate
            let outputFrameCount = AVAudioFrameCount(Double(pcmBuffer.frameLength) * ratio)
            guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputFrameCount) else { return }

            var error: NSError?
            converter.convert(to: outputBuffer, error: &error) { _, outStatus in
                outStatus.pointee = .haveData
                return pcmBuffer
            }

            if let channelData = outputBuffer.floatChannelData?[0] {
                let samples = Array(UnsafeBufferPointer(start: channelData, count: Int(outputBuffer.frameLength)))
                self.lock.lock()
                self.buffer.append(contentsOf: samples)
                if self.buffer.count > self.windowSamples {
                    self.buffer.removeFirst(self.buffer.count - self.windowSamples)
                }
                self.lock.unlock()
            }
        }

        engine.prepare()
        try? engine.start()
    }

    func stopCapture() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }

    func getMetrics() -> AudioMetrics {
        lock.lock()
        let samples = buffer
        lock.unlock()

        guard !samples.isEmpty else {
            return AudioMetrics(volumeRms: 0, silenceRatio: 1, estimatedWpm: 0, peakVolume: 0, volumeVariance: 0)
        }

        // volume_rms
        let sumSquares = samples.reduce(0.0) { $0 + Double($1) * Double($1) }
        let rms = min(1.0, sqrt(sumSquares / Double(samples.count)) * 3.0)

        // silence_ratio
        let silenceThreshold: Float = 0.02
        let silentCount = samples.filter { abs($0) < silenceThreshold }.count
        let silenceRatio = Double(silentCount) / Double(samples.count)

        // estimated_wpm (burst counting)
        let burstOnThreshold: Float = 0.04
        let burstOffThreshold: Float = 0.025
        var inBurst = false
        var bursts = 0
        for s in samples {
            let absS = abs(s)
            if !inBurst && absS > burstOnThreshold {
                inBurst = true
                bursts += 1
            } else if inBurst && absS < burstOffThreshold {
                inBurst = false
            }
        }
        let wpm = min(350, Int((Double(bursts) / 1.5) * 60))

        // peak_volume
        let peak = min(1.0, Double(samples.map { abs($0) }.max() ?? 0) * 2.0)

        // volume_variance (100ms chunks = 1600 samples)
        let chunkSize = 1600
        var chunkRMSValues: [Double] = []
        var i = 0
        while i + chunkSize <= samples.count {
            let chunk = samples[i..<(i + chunkSize)]
            let chunkSumSq = chunk.reduce(0.0) { $0 + Double($1) * Double($1) }
            chunkRMSValues.append(sqrt(chunkSumSq / Double(chunkSize)))
            i += chunkSize
        }
        var variance: Double = 0
        if chunkRMSValues.count > 1 {
            let mean = chunkRMSValues.reduce(0, +) / Double(chunkRMSValues.count)
            variance = chunkRMSValues.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / Double(chunkRMSValues.count)
        }

        return AudioMetrics(
            volumeRms: rms,
            silenceRatio: silenceRatio,
            estimatedWpm: wpm,
            peakVolume: peak,
            volumeVariance: variance
        )
    }

    func getWAVData() -> Data {
        lock.lock()
        let samples = buffer
        lock.unlock()

        // Convert Float32 to Int16 PCM
        var pcmData = Data()
        for s in samples {
            let clamped = max(-1.0, min(1.0, s))
            var int16 = Int16(clamped * 32767)
            pcmData.append(Data(bytes: &int16, count: 2))
        }

        // WAV header
        let dataSize = UInt32(pcmData.count)
        let fileSize = UInt32(36 + pcmData.count)
        let sampleRateInt: UInt32 = 16000
        let byteRate: UInt32 = 32000 // 16000 * 1 * 2
        let blockAlign: UInt16 = 2
        let bitsPerSample: UInt16 = 16
        let numChannels: UInt16 = 1

        var header = Data()
        header.append(contentsOf: "RIFF".utf8)
        header.append(withUnsafeBytes(of: fileSize.littleEndian) { Data($0) })
        header.append(contentsOf: "WAVE".utf8)
        header.append(contentsOf: "fmt ".utf8)
        header.append(withUnsafeBytes(of: UInt32(16).littleEndian) { Data($0) }) // chunk size
        header.append(withUnsafeBytes(of: UInt16(1).littleEndian) { Data($0) })  // PCM format
        header.append(withUnsafeBytes(of: numChannels.littleEndian) { Data($0) })
        header.append(withUnsafeBytes(of: sampleRateInt.littleEndian) { Data($0) })
        header.append(withUnsafeBytes(of: byteRate.littleEndian) { Data($0) })
        header.append(withUnsafeBytes(of: blockAlign.littleEndian) { Data($0) })
        header.append(withUnsafeBytes(of: bitsPerSample.littleEndian) { Data($0) })
        header.append(contentsOf: "data".utf8)
        header.append(withUnsafeBytes(of: dataSize.littleEndian) { Data($0) })

        return header + pcmData
    }
}
