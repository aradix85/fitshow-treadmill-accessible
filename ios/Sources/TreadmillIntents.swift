import AppIntents

/// Every intent returns a spoken sentence, so Siri reads back what happened.
/// `openAppWhenRun = false` keeps the app in the background — the Bluetooth
/// connection lives in the same process, so the command runs without any UI.

struct StartTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband starten"
    static var description = IntentDescription("Start de band op de laagste snelheid.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        .result(dialog: IntentDialog(stringLiteral: try await Treadmill.shared.start()))
    }
}

struct StopTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband stoppen"
    static var description = IntentDescription("Stopt de band. Dit is geen noodstop.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        .result(dialog: IntentDialog(stringLiteral: try await Treadmill.shared.stop()))
    }
}

struct FasterIntent: AppIntent {
    static var title: LocalizedStringResource = "Sneller"
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeSpeed(by: Limits.speedStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct SlowerIntent: AppIntent {
    static var title: LocalizedStringResource = "Langzamer"
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeSpeed(by: -Limits.speedStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct SteeperIntent: AppIntent {
    static var title: LocalizedStringResource = "Steiler"
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeIncline(by: Limits.inclineStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct FlatterIntent: AppIntent {
    static var title: LocalizedStringResource = "Vlakker"
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeIncline(by: -Limits.inclineStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

/// The one that pays for itself: "zeven" instead of twelve times "sneller".
struct SetSpeedIntent: AppIntent {
    static var title: LocalizedStringResource = "Snelheid instellen"
    static var openAppWhenRun = false

    @Parameter(title: "Snelheid in km/h",
               requestValueDialog: IntentDialog("Welke snelheid?"),
               inclusiveRange: (Limits.speedMin, Limits.speedMax))
    var speed: Double

    static var parameterSummary: some ParameterSummary {
        Summary("Zet de loopband op \(\.$speed) kilometer per uur")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.setSpeed(speed)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct SetInclineIntent: AppIntent {
    static var title: LocalizedStringResource = "Helling instellen"
    static var openAppWhenRun = false

    @Parameter(title: "Helling in procent",
               requestValueDialog: IntentDialog("Welke helling?"),
               inclusiveRange: (Limits.inclineMin, Limits.inclineMax))
    var incline: Double

    static var parameterSummary: some ParameterSummary {
        Summary("Zet de helling op \(\.$incline) procent")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.setIncline(incline)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct TreadmillStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopbandstatus"
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.statusSentence()
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

/// Ready-made Siri phrases, available without any user setup.
/// Apple scopes the com.apple.developer.siri entitlement to Intents app
/// extensions handling Siri requests *other than shortcut requests* — this app
/// has no extension and these are shortcut requests, so it should not apply.
/// If Siri ignores the phrases anyway, make your own shortcut instead and give
/// it whatever name you like; that route never needs an entitlement.
/// Note that Apple requires the app name inside each phrase.
struct LoopbandShortcuts: AppShortcutsProvider {
    // Without @AppShortcutsBuilder, Siri only ever recognises the FIRST entry.
    @AppShortcutsBuilder
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: FasterIntent(),
                    phrases: ["Sneller in \(.applicationName)"],
                    shortTitle: "Sneller", systemImageName: "hare")
        AppShortcut(intent: SlowerIntent(),
                    phrases: ["Langzamer in \(.applicationName)"],
                    shortTitle: "Langzamer", systemImageName: "tortoise")
        AppShortcut(intent: StartTreadmillIntent(),
                    phrases: ["Start \(.applicationName)"],
                    shortTitle: "Starten", systemImageName: "play")
        AppShortcut(intent: StopTreadmillIntent(),
                    phrases: ["Stop \(.applicationName)"],
                    shortTitle: "Stoppen", systemImageName: "stop")
        AppShortcut(intent: TreadmillStatusIntent(),
                    phrases: ["Status van \(.applicationName)"],
                    shortTitle: "Status", systemImageName: "info.circle")
    }
}
