"""
Correleert het onbekende 5-byte pakket op 2ACD met alles wat we wel kennen,
en leest tegelijk de FitShow UART-brug op fff1 mee.

Snelheden zijn zo gekozen dat ze onderscheid maken tussen de hypotheses:
  5 km/h -> mph afgekapt = 3, km/h gedeeld door 2 = 2
  7 km/h -> mph afgekapt = 4, km/h gedeeld door 2 = 3
"""

import asyncio, time
from bleak import BleakClient, BleakScanner

CTRL  = "00002ad9-0000-1000-8000-00805f9b34fb"
DATA  = "00002acd-0000-1000-8000-00805f9b34fb"
TRAIN = "00002ad3-0000-1000-8000-00805f9b34fb"
FFF1  = "0000fff1-0000-1000-8000-00805f9b34fb"
FFE4  = "0000ffe4-0000-1000-8000-00805f9b34fb"
B001  = "0000b001-0000-1000-8000-00805f9b34fb"
B002  = "0000b002-0000-1000-8000-00805f9b34fb"

log = open("mysterie.txt", "w", encoding="utf-8")
laatst = {"spd": 0.0, "afst": 0, "tijd": 0, "kcal": 0, "helling": 0.0}

def zeg(s):
    print(s)
    log.write(s + "\n")
    log.flush()

def op_data(_, d):
    b = bytes(d)
    t = time.strftime("%H:%M:%S")
    if len(b) >= 19:
        laatst["spd"]     = int.from_bytes(b[2:4], "little") / 100
        laatst["afst"]    = int.from_bytes(b[4:7], "little")
        laatst["helling"] = int.from_bytes(b[7:9], "little", signed=True) / 10
        laatst["kcal"]    = int.from_bytes(b[11:13], "little")
        laatst["tijd"]    = int.from_bytes(b[17:19], "little")
    else:
        # het raadselpakket: vlaggen + 3 databytes
        x, y, z = b[2], b[3], b[4]
        zeg(f"[{t}] MYSTERIE {x:3d} {y:3d} {z:3d}   "
            f"| ftms-snelheid {laatst['spd']:5.2f}  helling {laatst['helling']:4.1f}"
            f"  afstand {laatst['afst']:4d}  tijd {laatst['tijd']:4d}  kcal {laatst['kcal']:3d}"
            f"  | x als mph->km/h {x*1.609:5.2f}  x/2 {x/2:4.1f}")

def maak_logger(naam):
    def cb(_, d):
        zeg(f"[{time.strftime('%H:%M:%S')}] {naam:5s} " + bytes(d).hex(" "))
    return cb

def op_train(_, d):
    b = bytes(d)
    if len(b) >= 2:
        codes = {0x01: "idle", 0x0d: "loopt", 0x0e: "opwarmen", 0x0f: "afkoelen"}
        zeg(f"[{time.strftime('%H:%M:%S')}] STATUS {codes.get(b[1], hex(b[1]))}")

async def zet(c, payload, wat):
    zeg("")
    zeg(f">>> {wat}")
    await c.write_gatt_char(CTRL, payload, response=True)
    await asyncio.sleep(0.3)

def snelheid(kmh):
    return bytes([0x02]) + int(round(kmh * 100)).to_bytes(2, "little")

async def main():
    devices = await BleakScanner.discover(timeout=8.0)
    doel = next((d for d in devices if (d.name or "").startswith(("FS-", "SYMK"))), None)
    if not doel:
        zeg("Loopband niet gevonden.")
        return

    async with BleakClient(doel.address) as c:
        await c.start_notify(DATA, op_data)
        await c.start_notify(TRAIN, op_train)
        for uuid, naam in ((FFF1, "FFF1"), (FFE4, "FFE4"), (B001, "B001"), (B002, "B002")):
            try:
                await c.start_notify(uuid, maak_logger(naam))
            except Exception as e:
                zeg(f"(geen notify op {naam}: {e})")

        await c.write_gatt_char(CTRL, bytes([0x00]), response=True)
        await asyncio.sleep(2)

        try:
            await zet(c, bytes([0x01]), "reset")
            await zet(c, bytes([0x07]), "start")
            await asyncio.sleep(6)

            for kmh in (5.0, 7.0, 3.0):
                await zet(c, snelheid(kmh), f"snelheid {kmh} km/h")
                await asyncio.sleep(22)

            await zet(c, bytes([0x03, 0x32, 0x00]), "helling 5%")
            await asyncio.sleep(18)
            await zet(c, bytes([0x03, 0x00, 0x00]), "helling 0%")
            await asyncio.sleep(12)
        finally:
            await zet(c, bytes([0x08, 0x01]), "stop")
            await asyncio.sleep(14)

    zeg("")
    zeg("Klaar. Alles staat in mysterie.txt")

asyncio.run(main())
