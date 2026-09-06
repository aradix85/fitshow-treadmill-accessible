import CoreBluetooth
import Foundation

/// Bluetooth constants for the Fitness Machine Service.
/// Everything here comes straight from docs/PROTOCOL.md.
enum FTMS {
    static let service        = CBUUID(string: "1826")
    static let controlPoint   = CBUUID(string: "2AD9")
    static let treadmillData  = CBUUID(string: "2ACD")
    static let trainingStatus = CBUUID(string: "2AD3")
    static let machineStatus  = CBUUID(string: "2ADA")

    static let opRequestControl: UInt8 = 0x00
    static let opReset: UInt8          = 0x01
    static let opSetSpeed: UInt8       = 0x02
    static let opSetIncline: UInt8     = 0x03
    static let opStart: UInt8          = 0x07
    static let opStop: UInt8           = 0x08
}

/// Limits and step sizes. Mirrors the constants at the top of tr600i_server.py.
enum Limits {
    /// The speed the treadmill puts itself at on start; it ignores any value
    /// you set beforehand, so this is a fact about the machine, not a choice.
    static let speedStart  = 0.8
    static let speedMin    = 0.8
    static let speedMax    = 22.0
    static let speedStep   = 0.5
    static let inclineMin  = 0.0
    static let inclineMax  = 15.0
    static let inclineStep = 1.0

    /// Level the belt out when you stop, so you never step onto an incline you
    /// forgot about. Set to false if you would rather keep the setting.
    static let levelInclineOnStop = true
}

enum TreadmillError: LocalizedError {
    case bluetoothOff
    case notFound
    case timedOut
    case rejected
    case noReply

    var errorDescription: String? {
        switch self {
        case .bluetoothOff: return "Bluetooth staat uit."
        case .notFound:     return "Loopband niet gevonden."
        case .timedOut:     return "Geen verbinding met de loopband."
        case .rejected:     return "De loopband weigerde het commando."
        case .noReply:      return "De loopband bevestigde niets."
        }
    }
}

/// Spoken-friendly number formatting: "6,5" rather than "6.5".
func spoken(_ value: Double, decimals: Int = 1) -> String {
    let f = NumberFormatter()
    f.locale = Locale(identifier: "nl_NL")
    f.minimumFractionDigits = 0
    f.maximumFractionDigits = decimals
    return f.string(from: NSNumber(value: value)) ?? "\(value)"
}
