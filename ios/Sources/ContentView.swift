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

    /// Tap to hear the numbers. It deliberately does not announce on its own.
    private var statusArea: some View {
        Button {
            Task {
                let line = (try? await treadmill.statusSentence()) ?? treadmill.statusText
                announce(line)
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text(treadmill.statusText).font(.headline)
                Text("\(spoken(treadmill.speed)) km/u · \(spoken(treadmill.incline, decimals: 0))% · "
                     + "\(spoken(Double(treadmill.distanceM) / 1000, decimals: 2)) km")
                    .font(.title3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Status. Dubbeltik om snelheid, helling, afstand en tijd te horen.")
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
            Task {
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

/// Announcements are how VoiceOver users hear the result of a button press.
func announce(_ message: String) {
    UIAccessibility.post(notification: .announcement, argument: message)
}
