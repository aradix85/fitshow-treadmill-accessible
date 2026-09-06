import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject private var treadmill: Treadmill

    var body: some View {
        VStack(spacing: 12) {
            statusArea
            BigButton("Start") { try await treadmill.start() }
            HStack(spacing: 12) {
                BigButton("Langzamer") { try await treadmill.changeSpeed(by: -Limits.speedStep) }
                BigButton("Sneller")   { try await treadmill.changeSpeed(by:  Limits.speedStep) }
            }
            HStack(spacing: 12) {
                BigButton("Vlakker") { try await treadmill.changeIncline(by: -Limits.inclineStep) }
                BigButton("Steiler") { try await treadmill.changeIncline(by:  Limits.inclineStep) }
            }
            BigButton("Stop", tint: .red) { try await treadmill.stop() }
        }
        .padding()
    }

    /// The numbers live in the accessibility label itself, so swiping here reads
    /// the real parsed values without an announcement being involved at all.
    /// Double-tapping still speaks the full sentence.
    private var statusArea: some View {
        let minutes = treadmill.elapsedS / 60
        let seconds = treadmill.elapsedS % 60
        let km = Double(treadmill.distanceM) / 1000
        let spokenValues = "\(spoken(treadmill.speed)) kilometer per uur, "
            + "helling \(spoken(treadmill.incline, decimals: 0)) procent, "
            + "\(spoken(km, decimals: 2)) kilometer, "
            + "\(minutes) minuten \(seconds) seconden, "
            + "\(treadmill.kcal) calorieën"

        return Button {
            Task { @MainActor in
                let line = (try? await treadmill.statusSentence()) ?? treadmill.statusText
                announce(line)
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text(treadmill.statusText).font(.headline)
                Text(spokenValues).font(.title3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dutch("\(treadmill.statusText). \(spokenValues)"))
        .accessibilityHint(dutch("Dubbeltik om het opnieuw te horen."))
    }
}

/// A large, high-contrast button that speaks its result afterwards.
struct BigButton: View {
    private let title: String
    private let tint: Color
    private let action: () async throws -> String

    init(_ title: String, tint: Color = .accentColor,
         action: @escaping () async throws -> String) {
        self.title = title
        self.tint = tint
        self.action = action
    }

    var body: some View {
        Button {
            Task { @MainActor in
                do    { announce(try await action()) }
                catch { announce(error.localizedDescription) }
            }
        } label: {
            Text(title)
                .font(.title2.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 72)
        }
        .buttonStyle(.borderedProminent)
        .tint(tint)
    }
}

/// Announcements posted at the default priority are dropped whenever VoiceOver
/// is already talking — and right after a button press it always is, because it
/// is still reading the button's own label. High priority interrupts instead.
/// The language is spelled out too, so VoiceOver never falls back to an English
/// voice for Dutch text.
/// With VoiceOver off there is nobody to announce to, so we speak it ourselves.
func announce(_ message: String) {
    guard UIAccessibility.isVoiceOverRunning else {
        Task { await Speaker.shared.say(message) }
        return
    }
    let attributed = AttributedString(message, attributes: AttributeContainer([
        .accessibilitySpeechAnnouncementPriority: UIAccessibilityPriority.high,
        .accessibilitySpeechLanguage: "nl-NL"
    ]))
    AccessibilityNotification.Announcement(attributed).post()
}

/// Tags a label as Dutch so VoiceOver reads it with a Dutch voice.
func dutch(_ text: String) -> Text {
    Text(AttributedString(text, attributes: AttributeContainer([
        .accessibilitySpeechLanguage: "nl-NL"
    ])))
}
