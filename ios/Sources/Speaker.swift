import AVFoundation

/// Speaks a line through whatever you're listening on, ducking your music.
///
/// The intents used to hand their sentence to Siri as a dialog result, but that
/// only gets read aloud in some invocation paths. Doing it ourselves works the
/// same way every time, and lands in the headphones you're already wearing.
final class Speaker: NSObject, AVSpeechSynthesizerDelegate {

    static let shared = Speaker()

    private let synth = AVSpeechSynthesizer()
    private var finished: (() -> Void)?

    private override init() {
        super.init()
        synth.delegate = self
    }

    /// Returns once the sentence has actually been spoken, so the intent does
    /// not finish (and let iOS suspend us) halfway through a word.
    func say(_ text: String) async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            DispatchQueue.main.async {
                let session = AVAudioSession.sharedInstance()
                try? session.setCategory(.playback, mode: .spokenAudio,
                                         options: [.duckOthers,
                                                   .interruptSpokenAudioAndMixWithOthers])
                try? session.setActive(true)

                self.finished = { cont.resume() }

                let u = AVSpeechUtterance(string: text)
                u.voice = AVSpeechSynthesisVoice(language: "nl-NL")
                u.rate = AVSpeechUtteranceDefaultSpeechRate
                self.synth.speak(u)
            }
        }
    }

    private func done() {
        try? AVAudioSession.sharedInstance().setActive(
            false, options: .notifyOthersOnDeactivation)   // laat Spotify weer opkomen
        finished?()
        finished = nil
    }

    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { done() }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { done() }
}
