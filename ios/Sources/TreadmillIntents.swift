import AppIntents

/// Every intent hands its sentence back to Siri as a dialog result. Siri then
/// speaks it and, just as importantly, knows the request is finished — leaving
/// it out made Siri sit there waiting after every command.
///
/// The app deliberately does NOT speak here: that would double up with Siri.
/// Speaking in the app is only for the on-screen buttons (see ContentView).

struct StartTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband starten"
    static var description = IntentDescription("Start de band op de laagste snelheid.")
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        .result(dialog: IntentDialog(stringLiteral: try await Treadmill.shared.start()))
    }
}

struct StopTreadmillIntent: AppIntent {
    static var title: LocalizedStringResource = "Loopband stoppen"
    static var description = IntentDescription("Stopt de band. Dit is geen noodstop.")
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        .result(dialog: IntentDialog(stringLiteral: try await Treadmill.shared.stop()))
    }
}

struct FasterIntent: AppIntent {
    static var title: LocalizedStringResource = "Sneller"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeSpeed(by: Limits.speedStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct SlowerIntent: AppIntent {
    static var title: LocalizedStringResource = "Langzamer"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeSpeed(by: -Limits.speedStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct SteeperIntent: AppIntent {
    static var title: LocalizedStringResource = "Steiler"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeIncline(by: Limits.inclineStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

struct FlatterIntent: AppIntent {
    static var title: LocalizedStringResource = "Vlakker"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.changeIncline(by: -Limits.inclineStep)
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

/// De reden dat we hieraan begonnen: "zeven" in plaats van twaalf keer "sneller".
/// Maak hier een opdracht van met het veld LEEG, dan vraagt Siri om een getal.
struct SetSpeedIntent: AppIntent {
    static var title: LocalizedStringResource = "Snelheid instellen"
    static var openAppWhenRun = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    // inclusiveRange moet vóór requestValueDialog staan, met letterlijke waarden.
    @Parameter(title: "Snelheid in km/h",
               inclusiveRange: (0.8, 22.0),
               requestValueDialog: IntentDialog("Welke snelheid?"))
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
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    @Parameter(title: "Helling in procent",
               inclusiveRange: (0.0, 15.0),
               requestValueDialog: IntentDialog("Welke helling?"))
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
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let line = try await Treadmill.shared.statusSentence()
        return .result(dialog: IntentDialog(stringLiteral: line))
    }
}

// Er is bewust GEEN AppShortcutsProvider meer.
//
// Apple eist dat zo'n kant-en-klare zin de app-naam bevat ("stoppen in
// Loopband"), en juist de woorden die je nodig hebt — starten, stoppen,
// steiler — zijn bij Siri al bezet door ingebouwde functies. Die zinnen kwamen
// dus nooit bij deze app uit.
//
// Een opdracht die je zelf in de Opdrachten-app maakt heeft dat probleem niet:
// je kiest de naam, en Siri roept hem daarmee aan. Dus alleen "Bandje uit" in
// plaats van "stoppen in Loopband". De acties hieronder verschijnen gewoon in
// de actielijst van de Opdrachten-app, ook zonder provider.
