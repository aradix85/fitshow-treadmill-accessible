import AppIntents

/// Every intent speaks its own sentence via Speaker rather than returning a
/// dialog, because dialog results are not read aloud in every invocation path.
/// Errors still surface through Siri the normal way.

/// Shared plumbing: run a treadmill command, say the result, done.
@discardableResult
private func runAndSpeak(_ work: () async throws -> String) async throws -> String {
    let line = try await work()
    await Speaker.shared.say(line)
    return line
}

struct StartTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband starten"
    static var description = IntentDescription("Start de band op de laagste snelheid.")
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.start() }
        return .result()
    }
}

struct StopTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband stoppen"
    static var description = IntentDescription("Stopt de band. Dit is geen noodstop.")
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.stop() }
        return .result()
    }
}

struct FasterIntent: AppIntent {
    static var title: LocalizedStringResource = "Sneller"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.changeSpeed(by: Limits.speedStep) }
        return .result()
    }
}

struct SlowerIntent: AppIntent {
    static var title: LocalizedStringResource = "Langzamer"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.changeSpeed(by: -Limits.speedStep) }
        return .result()
    }
}

struct SteeperIntent: AppIntent {
    static var title: LocalizedStringResource = "Steiler"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.changeIncline(by: Limits.inclineStep) }
        return .result()
    }
}

struct FlatterIntent: AppIntent {
    static var title: LocalizedStringResource = "Vlakker"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.changeIncline(by: -Limits.inclineStep) }
        return .result()
    }
}

/// De reden dat we hieraan begonnen: "zeven" in plaats van twaalf keer "sneller".
struct SetSpeedIntent: AppIntent {
    static var title: LocalizedStringResource = "Snelheid instellen"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    // inclusiveRange moet vóór requestValueDialog staan, met letterlijke waarden.
    @Parameter(title: "Snelheid in km/h",
               inclusiveRange: (1.0, 22.0),
               requestValueDialog: IntentDialog("Welke snelheid?"))
    var speed: Double

    static var parameterSummary: some ParameterSummary {
        Summary("Zet de loopband op \(\.$speed) kilometer per uur")
    }

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.setSpeed(speed) }
        return .result()
    }
}

struct SetInclineIntent: AppIntent {
    static var title: LocalizedStringResource = "Helling instellen"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    @Parameter(title: "Helling in procent",
               inclusiveRange: (0.0, 15.0),
               requestValueDialog: IntentDialog("Welke helling?"))
    var incline: Double

    static var parameterSummary: some ParameterSummary {
        Summary("Zet de helling op \(\.$incline) procent")
    }

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.setIncline(incline) }
        return .result()
    }
}

struct TreadmillStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopbandstatus"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult {
        try await runAndSpeak { try await Treadmill.shared.statusSentence() }
        return .result()
    }
}

/// Kant-en-klare Siri-zinnen. Apple vereist de app-naam in elke zin.
struct LoopbandShortcuts: AppShortcutsProvider {
    // Zonder @AppShortcutsBuilder herkent Siri alleen de EERSTE zin.
    @AppShortcutsBuilder
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: FasterIntent(),
                    phrases: ["Sneller in \(.applicationName)"],
                    shortTitle: "Sneller", systemImageName: "hare")
        AppShortcut(intent: SlowerIntent(),
                    phrases: ["Langzamer in \(.applicationName)"],
                    shortTitle: "Langzamer", systemImageName: "tortoise")
        AppShortcut(intent: SteeperIntent(),
                    phrases: ["Steiler in \(.applicationName)"],
                    shortTitle: "Steiler", systemImageName: "arrow.up.right")
        AppShortcut(intent: FlatterIntent(),
                    phrases: ["Vlakker in \(.applicationName)"],
                    shortTitle: "Vlakker", systemImageName: "arrow.down.right")
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
