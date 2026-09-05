import CoreBluetooth
import Combine
import Foundation

/// Holds the Bluetooth connection to the treadmill and exposes commands.
///
/// Everything runs on the main queue on purpose: CoreBluetooth is created with
/// `queue: .main`, so all delegate callbacks arrive there too and no locking is
/// needed anywhere in this file. That is also why @unchecked Sendable is safe.
final class Treadmill: NSObject, ObservableObject, @unchecked Sendable {

    static let shared = Treadmill()

    // MARK: - Published state (what the treadmill reports)

    @Published private(set) var statusText = "Niet verbonden"
    @Published private(set) var isConnected = false
    @Published private(set) var isRunning = false
    @Published private(set) var speed = 0.0        // km/h
    @Published private(set) var incline = 0.0      // %
    @Published private(set) var distanceM = 0
    @Published private(set) var elapsedS = 0
    @Published private(set) var kcal = 0

    // MARK: - What we asked for (the belt follows with a delay)

    private(set) var targetSpeed = Limits.speedStart
    private(set) var targetIncline = 0.0

    // MARK: - Bluetooth internals

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var controlPoint: CBCharacteristic?
    private var hasControl = false
    private var wantsConnection = false

    private var writeQueue: [[UInt8]] = []
    private var isWriting = false

    private var waiters: [(Error?) -> Void] = []
    private var timeoutTimer: Timer?

    /// One list of callbacks per opcode, resolved when the treadmill sends its
    /// `80 <opcode> <result>` indication back.
    fileprivate var ackWaiters: [UInt8: [(Error?) -> Void]] = [:]

    private static let savedIDKey = "treadmill.peripheral.identifier"

    private override init() {
        super.init()
        central = CBCentralManager(
            delegate: self,
            queue: .main,
            options: [CBCentralManagerOptionRestoreIdentifierKey: "nl.aradix.loopband.central"]
        )
    }

    var isReady: Bool { isConnected && hasControl && controlPoint != nil }
}

// MARK: - Connecting

extension Treadmill {

    /// Make sure we are connected and have control. Safe to call from anywhere.
    func ensureReady(timeout: TimeInterval = 15) async throws {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.main.async {
                if self.isReady { cont.resume(); return }
                self.waiters.append { error in
                    if let error { cont.resume(throwing: error) } else { cont.resume() }
                }
                self.scheduleTimeout(timeout)
                self.beginConnecting()
            }
        }
    }

    private func scheduleTimeout(_ seconds: TimeInterval) {
        timeoutTimer?.invalidate()
        timeoutTimer = Timer.scheduledTimer(withTimeInterval: seconds, repeats: false) { _ in
            DispatchQueue.main.async { self.finishWaiters(TreadmillError.timedOut) }
        }
    }

    private func finishWaiters(_ error: Error?) {
        timeoutTimer?.invalidate()
        timeoutTimer = nil
        let pending = waiters
        waiters.removeAll()
        pending.forEach { $0(error) }
    }

    private func beginConnecting() {
        wantsConnection = true
        guard central.state == .poweredOn else {
            if central.state == .poweredOff { finishWaiters(TreadmillError.bluetoothOff) }
            return   // .unknown / .resetting: wait for didUpdateState
        }
        if let p = peripheral, p.state == .connected { discover(on: p); return }

        // Prefer the treadmill we used last time: no scan needed, works in the background.
        if let saved = UserDefaults.standard.string(forKey: Self.savedIDKey),
           let uuid = UUID(uuidString: saved),
           let known = central.retrievePeripherals(withIdentifiers: [uuid]).first {
            connect(to: known)
            return
        }
        // First run only. Scan broadly, because not every FitShow module
        // advertises the FTMS service UUID — tr600i_server.py matches on name too.
        statusText = "Zoeken naar loopband…"
        central.scanForPeripherals(withServices: nil, options: nil)
    }

    private func connect(to p: CBPeripheral) {
        central.stopScan()
        peripheral = p
        p.delegate = self
        statusText = "Verbinden…"
        central.connect(p, options: nil)
    }

    private func discover(on p: CBPeripheral) {
        statusText = "Kanalen zoeken…"
        p.discoverServices([FTMS.service])
    }
}

// MARK: - CBCentralManagerDelegate

extension Treadmill: CBCentralManagerDelegate {

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            if wantsConnection { beginConnecting() }
        case .poweredOff:
            resetConnectionState(status: "Bluetooth staat uit.")
            finishWaiters(TreadmillError.bluetoothOff)
        case .unauthorized:
            resetConnectionState(status: "Geen Bluetooth-toestemming.")
            finishWaiters(TreadmillError.bluetoothOff)
        default:
            break
        }
    }

    func centralManager(_ central: CBCentralManager,
                        willRestoreState dict: [String: Any]) {
        if let restored = dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral],
           let p = restored.first {
            peripheral = p
            p.delegate = self
            wantsConnection = true
        }
    }

    func centralManager(_ central: CBCentralManager,
                        didDiscover p: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi RSSI: NSNumber) {
        let advertised = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        let looksRight = advertised.contains(FTMS.service)
            || name.hasPrefix("FS-")
            || name.hasPrefix("SYMK")
        guard looksRight else { return }
        connect(to: p)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        UserDefaults.standard.set(p.identifier.uuidString, forKey: Self.savedIDKey)
        isConnected = true
        discover(on: p)
    }

    func centralManager(_ central: CBCentralManager,
                        didFailToConnect p: CBPeripheral, error: Error?) {
        resetConnectionState(status: "Verbinden mislukt.")
        finishWaiters(TreadmillError.notFound)
    }

    func centralManager(_ central: CBCentralManager,
                        didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        resetConnectionState(status: "Verbinding verbroken.")
        if wantsConnection { central.connect(p, options: nil) }   // auto-reconnect
    }

    private func resetConnectionState(status: String) {
        isConnected = false
        hasControl = false
        controlPoint = nil
        isWriting = false
        writeQueue.removeAll()
        statusText = status
        // Don't leave a command hanging on a connection that no longer exists.
        let orphaned = ackWaiters.values.flatMap { $0 }
        ackWaiters.removeAll()
        orphaned.forEach { $0(TreadmillError.noReply) }
    }
}

// MARK: - CBPeripheralDelegate

extension Treadmill: CBPeripheralDelegate {

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        guard let service = p.services?.first(where: { $0.uuid == FTMS.service }) else {
            resetConnectionState(status: "Geen FTMS-service gevonden.")
            finishWaiters(TreadmillError.notFound)
            return
        }
        p.discoverCharacteristics(
            [FTMS.controlPoint, FTMS.treadmillData, FTMS.trainingStatus, FTMS.machineStatus],
            for: service
        )
    }

    func peripheral(_ p: CBPeripheral,
                    didDiscoverCharacteristicsFor service: CBService,
                    error: Error?) {
        for c in service.characteristics ?? [] {
            switch c.uuid {
            case FTMS.controlPoint:
                controlPoint = c
                p.setNotifyValue(true, for: c)     // control point uses indicate
                enqueue([FTMS.opRequestControl])
            case FTMS.treadmillData, FTMS.trainingStatus, FTMS.machineStatus:
                p.setNotifyValue(true, for: c)
            default:
                break
            }
        }
    }

    func peripheral(_ p: CBPeripheral,
                    didWriteValueFor c: CBCharacteristic,
                    error: Error?) {
        // The Python bridge waits 0.3 s between control-point writes; so do we.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            self.isWriting = false
            self.drainWriteQueue()
        }
    }

    func peripheral(_ p: CBPeripheral,
                    didUpdateValueFor c: CBCharacteristic,
                    error: Error?) {
        guard let data = c.value else { return }
        switch c.uuid {
        case FTMS.controlPoint:  handleControlResponse([UInt8](data))
        case FTMS.treadmillData: parseTreadmillData([UInt8](data))
        case FTMS.trainingStatus:
            if data.count >= 2 { isRunning = (data[1] == 0x0D || data[1] == 0x0E) }
        case FTMS.machineStatus:
            if let first = data.first, first == 0x02 { isRunning = false }
        default: break
        }
    }

    private func handleControlResponse(_ bytes: [UInt8]) {
        // Reply format: 80 <opcode> <result>, where 01 means success.
        guard bytes.count >= 3, bytes[0] == 0x80 else { return }
        let opcode = bytes[1]
        let accepted = bytes[2] == 0x01

        if opcode == FTMS.opRequestControl && accepted {
            hasControl = true
            statusText = "Verbonden."
            finishWaiters(nil)
        }

        // Release whoever is waiting on this particular command.
        let pending = ackWaiters.removeValue(forKey: opcode) ?? []
        pending.forEach { $0(accepted ? nil : TreadmillError.rejected) }
    }
}

// MARK: - Parsing Treadmill Data (2ACD)

extension Treadmill {

    /// Faithful port of parse_treadmill_data() in tr600i_server.py.
    /// Field order follows the flag bits; bit 0 == 0 means speed is present.
    private func parseTreadmillData(_ b: [UInt8]) {
        guard b.count >= 2 else { return }
        let flags = UInt16(b[0]) | (UInt16(b[1]) << 8)
        var i = 2

        func take(_ n: Int) -> Int? {
            guard i + n <= b.count else { return nil }
            var v = 0
            for k in 0..<n { v |= Int(b[i + k]) << (8 * k) }
            i += n
            return v
        }
        func signed16(_ v: Int) -> Int { v > 0x7FFF ? v - 0x10000 : v }
        func has(_ bit: Int) -> Bool { flags & (1 << bit) != 0 }

        if let v = take(2) { speed = Double(v) / 100 }
        if has(1) { _ = take(2) }                                   // average speed
        if has(2), let v = take(3) { distanceM = v }
        if has(3), i + 4 <= b.count {
            let raw = take(2) ?? 0
            incline = Double(signed16(raw)) / 10
            _ = take(2)                                             // ramp angle
        }
        if has(4) { _ = take(4) }                                   // pos/neg elevation
        if has(5) { _ = take(1) }                                   // pace
        if has(6) { _ = take(1) }                                   // average pace
        if has(7), i + 5 <= b.count {
            kcal = take(2) ?? 0
            _ = take(2)                                             // kcal per hour
            _ = take(1)                                             // kcal per minute
        }
        if has(8) { _ = take(1) }                                   // heart rate
        if has(9) { _ = take(1) }                                   // metabolic equivalent
        if has(10), let v = take(2) { elapsedS = v }
    }
}

// MARK: - Sending commands

extension Treadmill {

    private func enqueue(_ payload: [UInt8]) {
        writeQueue.append(payload)
        drainWriteQueue()
    }

    fileprivate func drainWriteQueue() {
        guard !isWriting, !writeQueue.isEmpty,
              let cp = controlPoint, let p = peripheral else { return }
        isWriting = true
        p.writeValue(Data(writeQueue.removeFirst()), for: cp, type: .withResponse)
    }

    /// Send a command and wait for the treadmill to acknowledge it.
    /// Nothing is spoken to the user until this returns without throwing, so a
    /// number you hear always means the treadmill actually took the command.
    private func send(_ payload: [UInt8], timeout: TimeInterval = 4) async throws {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.main.async {
                var settled = false
                let settle: (Error?) -> Void = { error in
                    guard !settled else { return }
                    settled = true
                    if let error { cont.resume(throwing: error) } else { cont.resume() }
                }
                self.ackWaiters[payload[0], default: []].append(settle)
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    settle(TreadmillError.noReply)
                }
                self.enqueue(payload)
            }
        }
    }

    private static func le16(_ value: Int) -> [UInt8] {
        let v = UInt16(bitPattern: Int16(clamping: value))
        return [UInt8(v & 0xFF), UInt8(v >> 8)]
    }

    // Each command returns the sentence Siri should speak back. The setpoint is
    // only updated after the treadmill confirms, so a rejected command never
    // leaves us with a wrong idea of where the belt is.

    @discardableResult
    func start() async throws -> String {
        try await ensureReady()
        try await send([FTMS.opReset])
        try await send([FTMS.opSetSpeed] + Self.le16(Int((Limits.speedStart * 100).rounded())))
        try await send([FTMS.opStart])
        targetSpeed = Limits.speedStart
        // isRunning is not set here: the treadmill reports it over 2AD3.
        return "Gestart op \(spoken(Limits.speedStart, decimals: 0)) kilometer per uur."
    }

    @discardableResult
    func stop() async throws -> String {
        try await ensureReady()
        try await send([FTMS.opStop, 0x01])
        targetSpeed = 0
        return "Gestopt."
    }

    @discardableResult
    func setSpeed(_ kmh: Double) async throws -> String {
        try await ensureReady()
        let clamped = min(Limits.speedMax, max(Limits.speedMin, (kmh * 10).rounded() / 10))
        try await send([FTMS.opSetSpeed] + Self.le16(Int((clamped * 100).rounded())))
        targetSpeed = clamped
        var line = "Snelheid \(spoken(clamped)) kilometer per uur."
        if clamped >= Limits.speedMax { line += " Dit is het maximum." }
        if !isRunning { line += " De band loopt niet." }
        return line
    }

    @discardableResult
    func setIncline(_ percent: Double) async throws -> String {
        try await ensureReady()
        let clamped = min(Limits.inclineMax, max(Limits.inclineMin, percent.rounded()))
        try await send([FTMS.opSetIncline] + Self.le16(Int((clamped * 10).rounded())))
        targetIncline = clamped
        var line = "Helling \(spoken(clamped, decimals: 0)) procent."
        if clamped >= Limits.inclineMax { line += " Dit is het maximum." }
        return line
    }

    @discardableResult
    func changeSpeed(by delta: Double) async throws -> String {
        try await setSpeed(targetSpeed + delta)
    }

    @discardableResult
    func changeIncline(by delta: Double) async throws -> String {
        try await setIncline(targetIncline + delta)
    }

    /// One spoken sentence with everything worth knowing mid-run.
    func statusSentence() async throws -> String {
        try await ensureReady()
        let minutes = elapsedS / 60
        let seconds = elapsedS % 60
        let km = Double(distanceM) / 1000
        return "\(spoken(speed)) kilometer per uur, helling \(spoken(incline, decimals: 0)) procent, "
            + "\(spoken(km, decimals: 2)) kilometer, \(minutes) minuten en \(seconds) seconden, "
            + "\(kcal) calorieën."
    }
}
