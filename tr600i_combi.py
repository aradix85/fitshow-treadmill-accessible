"""
TREADMILL CONTROL + SNIFFER in one (for reverse-engineering).

This is a control script WITH a built-in 'black box': you type commands
(start / speed X / incline X / stop) and meanwhile it listens on ALL
channels and writes everything to a log file. That lets you line up your
commands against the raw bytes and figure out where speed, distance and time
live.

One connection, you stay in control, all data captured.

START:
  python tr600i_combi.py

COMMANDS (type + Enter):
  start          -> start at 3 km/h
  start 3.5      -> start at 3.5 km/h
  speed 4        -> set speed to 4 km/h
  incline 2      -> set incline to value 2
  stop           -> stop the belt, standby
  show           -> show the last known readings (once)
  quit           -> disconnect and quit

EVERYTHING is also logged to 'sessie_log.txt' (commands AND incoming data,
with timestamps). Paste that file back into the chat afterwards.

TIP FOR GOOD DATA: start the treadmill, then change the speed a few times in
big steps (e.g. 3 -> 5 -> 2). More change makes it easier to see which bytes
move. Do this with the belt EMPTY.

SAFETY:
  - Test with the belt EMPTY first.
  - 'stop' is a deliberate stop, NOT your emergency brake. The physical STOP
    button and the safety key always work and are your real emergency stop.
"""

import asyncio
import sys
from datetime import datetime
from bleak import BleakClient, BleakScanner

# ---- Built-in settings ----
LOOPBAND_ADRES = "XX:XX:XX:XX:XX:XX"   # leave as-is to auto-detect
NAAM_HINTS = ("FS-", "SYMK")
STANDAARD_SNELHEID = 3.0
LOGBESTAND = "sessie_log.txt"
# ----------------------------

CONTROL_POINT_CHAR = "00002ad9-0000-1000-8000-00805f9b34fb"
TREADMILL_DATA_CHAR = "00002acd-0000-1000-8000-00805f9b34fb"
TRAINING_STATUS_CHAR = "00002ad3-0000-1000-8000-00805f9b34fb"
MACHINE_STATUS_CHAR = "00002ada-0000-1000-8000-00805f9b34fb"

OP_REQUEST_CONTROL = 0x00
OP_RESET = 0x01
OP_SET_SPEED = 0x02
OP_SET_INCLINE = 0x03
OP_START = 0x07
OP_STOP = 0x08

BEKENDE_UUIDS = {
    "00002acd-0000-1000-8000-00805f9b34fb": "FTMS Treadmill Data (standard)",
    "00002ad9-0000-1000-8000-00805f9b34fb": "FTMS Control Point (standard)",
    "00002ad3-0000-1000-8000-00805f9b34fb": "FTMS Training Status (standard)",
    "00002ada-0000-1000-8000-00805f9b34fb": "FTMS Machine Status (standard)",
    "00002acc-0000-1000-8000-00805f9b34fb": "FTMS Feature (standard)",
    "00002a37-0000-1000-8000-00805f9b34fb": "Heart Rate Measurement (standard)",
    "00002a19-0000-1000-8000-00805f9b34fb": "Battery Level (standard)",
}

# Last known readings
laatste_data = {}
laatste_ruw = None
laatste_status = "unknown"
ingesteld_snelheid = None
ingesteld_helling = None

_logbestand = None


def log(regel: str, ook_scherm: bool = True):
    """Write to the log file, and by default to the screen too."""
    if ook_scherm:
        print(regel)
    if _logbestand:
        _logbestand.write(regel + "\n")
        _logbestand.flush()


def log_stil(regel: str):
    """Log file only (for the silent data stream)."""
    log(regel, ook_scherm=False)


def beschrijf_uuid(uuid: str) -> str:
    naam = BEKENDE_UUIDS.get(uuid.lower())
    if naam:
        return f"{uuid} [{naam}]"
    korte = uuid.lower()
    if korte.startswith("0000fff") or korte.startswith("0000ffe"):
        return f"{uuid} [VENDOR CHANNEL - possibly the real data here!]"
    return f"{uuid} [unknown/vendor]"


def parse_treadmill_data(data: bytearray) -> dict:
    d = {}
    if len(data) < 2:
        return d
    flags = int.from_bytes(data[0:2], "little")
    i = 2
    if i + 2 <= len(data):
        d["speed"] = int.from_bytes(data[i:i+2], "little") / 100; i += 2
    if flags & (1 << 1) and i + 2 <= len(data):
        d["avg_speed"] = int.from_bytes(data[i:i+2], "little") / 100; i += 2
    if flags & (1 << 2) and i + 3 <= len(data):
        d["distance_m"] = int.from_bytes(data[i:i+3], "little"); i += 3
    if flags & (1 << 3) and i + 4 <= len(data):
        d["incline_pct"] = int.from_bytes(data[i:i+2], "little", signed=True) / 10; i += 4
    if flags & (1 << 4) and i + 4 <= len(data):
        d["elevation_m"] = int.from_bytes(data[i:i+2], "little") / 10; i += 4
    if flags & (1 << 5) and i + 1 <= len(data):
        d["pace"] = data[i] / 10; i += 1
    if flags & (1 << 7) and i + 5 <= len(data):
        d["calories"] = int.from_bytes(data[i:i+2], "little"); i += 5
    if flags & (1 << 8) and i + 1 <= len(data):
        d["heart_rate"] = data[i]; i += 1
    if flags & (1 << 10) and i + 2 <= len(data):
        s = int.from_bytes(data[i:i+2], "little"); d["time"] = f"{s//60}:{s%60:02d}"; i += 2
    return d


def toon_data():
    if ingesteld_snelheid is None:
        print("  Nothing started yet. Type 'start' or 'start 3' to begin.")
    else:
        eind = f", incline {ingesteld_helling}" if ingesteld_helling is not None else ""
        print(f"  [set] speed {ingesteld_snelheid} km/h{eind}")
    print(f"  [training status] {laatste_status}")
    if laatste_data:
        gemeten = ", ".join(f"{k} {v}" for k, v in laatste_data.items())
        print(f"  [measured by treadmill] {gemeten}")
    print(f"  [last raw FTMS data] {laatste_ruw}")
    print("  (All channels are being logged to the log file.)")


def duid_control_antwoord(data: bytearray) -> str:
    if len(data) >= 3 and data[0] == 0x80:
        results = {0x01: "OK (success)", 0x02: "opcode not supported",
                   0x03: "invalid parameter", 0x04: "operation failed",
                   0x05: "control not permitted"}
        return f"response to opcode {data[1]:#04x}: {results.get(data[2], f'code {data[2]}')}"
    return f"raw {data.hex()}"


def duid_machine_status(data: bytearray) -> str:
    if not data:
        return "empty"
    codes = {0x01: "reset", 0x02: "STOPPED by user (safety key?)",
             0x03: "stopped/paused", 0x04: "started/resumed",
             0x05: "speed changed", 0x06: "incline changed"}
    return codes.get(data[0], f"code {data[0]}")


async def vind_adres():
    """Find the treadmill automatically (see tr600i_server.py for details)."""
    adres_ingevuld = LOOPBAND_ADRES and LOOPBAND_ADRES.upper() != "XX:XX:XX:XX:XX:XX"

    if adres_ingevuld:
        print(f"Looking for the treadmill (first at configured address {LOOPBAND_ADRES})...")
    else:
        print("No fixed address set; auto-detecting a FitShow treadmill...")

    devices = await BleakScanner.discover(timeout=6.0)
    adressen = {d.address.upper(): (d.name or "") for d in devices}

    if adres_ingevuld and LOOPBAND_ADRES.upper() in adressen:
        print("Configured address found.")
        return LOOPBAND_ADRES
    if adres_ingevuld:
        print("Configured address not seen; trying by name anyway...")

    kandidaten = [(adr, naam) for adr, naam in adressen.items()
                  if any(h.lower() in naam.lower() for h in NAAM_HINTS)]

    if len(kandidaten) == 1:
        adr, naam = kandidaten[0]
        print(f"Auto-detected: '{naam}' at {adr}.")
        return adr

    if len(kandidaten) > 1:
        print("\nMultiple possible treadmills found:")
        for i, (adr, naam) in enumerate(kandidaten, 1):
            print(f"  {i}. '{naam}'  ->  {adr}")
        print("\nPick one by setting its address as LOOPBAND_ADRES near the top.")
        return None

    print("\nNo FitShow treadmill found. Is it on and is the FitShow app CLOSED?")
    return None


async def lees_commando():
    return await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)


async def sessie():
    global laatste_data, laatste_status, laatste_ruw
    global ingesteld_snelheid, ingesteld_helling

    adres = await vind_adres()
    if not adres:
        return

    log(f"\nConnecting to {adres} ...")
    async with BleakClient(adres) as client:
        log("Connected.\n")

        async def stuur(naam, payload):
            print(f"-> {naam}")
            t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_stil(f"{t} | COMMAND -> {naam} | bytes: {bytes(payload).hex()}")
            await client.write_gatt_char(CONTROL_POINT_CHAR, payload, response=True)
            await asyncio.sleep(0.5)

        # ---- Log the menu (services & characteristics) ----
        log_stil("\n================ MENU ================")
        alle_notify = []
        for service in client.services:
            log_stil(f"SERVICE {beschrijf_uuid(service.uuid)}")
            for c in service.characteristics:
                log_stil(f"   CHAR {beschrijf_uuid(c.uuid)} can: {','.join(c.properties)}")
                if "notify" in c.properties or "indicate" in c.properties:
                    alle_notify.append(c.uuid)
        log_stil("=====================================\n")

        # ---- Generic logger for EVERY channel (silent, log only) ----
        def maak_logger(uuid):
            beschrijving = beschrijf_uuid(uuid)
            def handler(_, data):
                t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                log_stil(f"{t} | DATA {beschrijving} | bytes: {bytes(data).hex()}")
            return handler

        def op_data(_, d):
            global laatste_data, laatste_ruw
            laatste_ruw = bytes(d).hex()
            parsed = parse_treadmill_data(d)
            if parsed:
                laatste_data = parsed

        def op_status(_, d):
            global laatste_status
            if len(d) >= 2:
                codes = {0x01: "ready", 0x02: "warming up",
                         0x0D: "running", 0x0E: "cooling down"}
                laatste_status = codes.get(d[1], f"code {d[1]}")

        def op_antwoord(_, d):
            tekst = duid_control_antwoord(d)
            print(f"  [response] {tekst}")
            t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_stil(f"{t} | RESPONSE control point | {tekst} | bytes: {bytes(d).hex()}")

        def op_machine(_, d):
            tekst = duid_machine_status(d)
            print(f"  [machine] {tekst}")
            t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_stil(f"{t} | MACHINE STATUS | {tekst} | bytes: {bytes(d).hex()}")

        # Put the silent logger on EVERY notify channel...
        for uuid in alle_notify:
            try:
                await client.start_notify(uuid, maak_logger(uuid))
            except Exception as e:
                log_stil(f"(could not listen on {uuid}: {e})")

        # ...and on the known channels, a combined handler that also does the
        # on-screen behavior.
        bekend = {
            CONTROL_POINT_CHAR: op_antwoord,
            TREADMILL_DATA_CHAR: op_data,
            TRAINING_STATUS_CHAR: op_status,
            MACHINE_STATUS_CHAR: op_machine,
        }
        char_uuids = {c.uuid.lower() for s in client.services for c in s.characteristics}
        for uuid, handler in bekend.items():
            if uuid in char_uuids:
                try:
                    await client.stop_notify(uuid)
                except Exception:
                    pass
                def maak_combi(u, nette):
                    logger = maak_logger(u)
                    def combi(sender, data):
                        logger(sender, data)   # log first
                        nette(sender, data)    # then screen behavior
                    return combi
                try:
                    await client.start_notify(uuid, maak_combi(uuid, handler))
                except Exception as e:
                    log_stil(f"(could not set known handler on {uuid}: {e})")

        await stuur("request control", bytes([OP_REQUEST_CONTROL]))

        print("\nReady for commands. (Screen stays quiet; everything goes to the log.)")
        print("start [speed] / speed X / incline X / stop / show / quit\n")
        print("TIP: start, then change speed in big steps,")
        print("e.g. 3 -> 5 -> 2, with the belt EMPTY. That gives the best data.\n")

        while True:
            regel = (await lees_commando()).strip().lower()
            if not regel:
                continue
            delen = regel.split()
            cmd = delen[0]

            if cmd == "quit":
                log("Disconnecting...")
                break
            elif cmd == "start":
                spd = float(delen[1]) if len(delen) > 1 else STANDAARD_SNELHEID
                await stuur("reset", bytes([OP_RESET]))
                v = int(round(spd * 100))
                await stuur(f"speed {spd} km/h", bytes([OP_SET_SPEED]) + v.to_bytes(2, "little"))
                await stuur("start", bytes([OP_START]))
                ingesteld_snelheid = spd
            elif cmd == "speed" and len(delen) > 1:
                spd = float(delen[1]); v = int(round(spd * 100))
                await stuur(f"speed {spd} km/h", bytes([OP_SET_SPEED]) + v.to_bytes(2, "little"))
                ingesteld_snelheid = spd
            elif cmd == "incline" and len(delen) > 1:
                h = float(delen[1]); v = int(round(h * 10))
                await stuur(f"incline {h}", bytes([OP_SET_INCLINE]) + v.to_bytes(2, "little", signed=True))
                ingesteld_helling = h
            elif cmd == "stop":
                await stuur("stop", bytes([OP_STOP, 0x01]))
            elif cmd == "show":
                toon_data()
            else:
                print("  unknown. Use: start / speed X / incline X / stop / show / quit")

    log("\nDone. The belt keeps running until you sent 'stop' or used the STOP button / key.")
    log(f"The full log is in '{LOGBESTAND}'. Paste it into the chat.")


def main():
    global _logbestand
    _logbestand = open(LOGBESTAND, "w", encoding="utf-8")
    _logbestand.write(f"=== treadmill combi session {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    try:
        asyncio.run(sessie())
    finally:
        if _logbestand:
            _logbestand.close()


if __name__ == "__main__":
    main()
