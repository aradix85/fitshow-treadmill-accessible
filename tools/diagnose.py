"""
Diagnose voor de FitShow/FTMS loopband.

Verbindt, luistert mee, en legt van elk Treadmill Data-pakket vast hoe lang het
is, welke vlaggen erin staan, welke lengte die vlaggen voorspellen, en de ruwe
bytes. Zo zien we of de vlaggen kloppen met de werkelijkheid.

Test daarnaast of de loopband een bevestiging terugstuurt op een commando.

BELANGRIJK: de iPhone-app mag NIET verbonden zijn; de band accepteert er maar een.
"""

import asyncio, time
from bleak import BleakClient, BleakScanner

CTRL  = "00002ad9-0000-1000-8000-00805f9b34fb"
DATA  = "00002acd-0000-1000-8000-00805f9b34fb"
TRAIN = "00002ad3-0000-1000-8000-00805f9b34fb"
MACH  = "00002ada-0000-1000-8000-00805f9b34fb"

# (vlagbit, naam, aantal bytes) in FTMS-volgorde
VELDEN = [
    (1,  "gemiddelde snelheid", 2),
    (2,  "afstand", 3),
    (3,  "helling + hellingshoek", 4),
    (4,  "hoogtewinst pos+neg", 4),
    (5,  "tempo", 1),
    (6,  "gemiddeld tempo", 1),
    (7,  "energie totaal+uur+min", 5),
    (8,  "hartslag", 1),
    (9,  "metabool equivalent", 1),
    (10, "verstreken tijd", 2),
    (11, "resterende tijd", 2),
]

log = open("loopband-diagnose.txt", "w", encoding="utf-8")

def zeg(s):
    print(s)
    log.write(s + "\n")
    log.flush()

gezien = set()

def op_data(_, d):
    b = bytes(d)
    flags = int.from_bytes(b[0:2], "little")
    verwacht = 2 + (0 if flags & 1 else 2)          # vlaggen + momentane snelheid
    aanwezig = []
    for bit, naam, n in VELDEN:
        if flags & (1 << bit):
            verwacht += n
            aanwezig.append(f"{naam}({n})")
    sleutel = (len(b), flags)
    if sleutel not in gezien:
        gezien.add(sleutel)
        zeg("")
        zeg(f"=== NIEUW PAKKETTYPE: {len(b)} bytes, vlaggen 0x{flags:04X} ===")
        zeg(f"    vlaggen zeggen: {', '.join(aanwezig) or 'alleen snelheid'}")
        oordeel = "klopt" if verwacht == len(b) else "KOMT NIET OVEREEN"
        zeg(f"    voorspeld {verwacht} bytes, werkelijk {len(b)} bytes  <-- {oordeel}")
    zeg(f"[{time.strftime('%H:%M:%S')}] DATA {len(b):2d}B  " + b.hex(" "))

def op_ctrl(_, d):
    zeg(f"[{time.strftime('%H:%M:%S')}] BEVESTIGING  " + bytes(d).hex(" "))

def op_train(_, d):
    zeg(f"[{time.strftime('%H:%M:%S')}] TRAINING     " + bytes(d).hex(" "))

def op_mach(_, d):
    zeg(f"[{time.strftime('%H:%M:%S')}] MACHINE      " + bytes(d).hex(" "))

async def main():
    zeg("Zoeken naar de loopband (zorg dat de iPhone-app niet verbonden is)...")
    devices = await BleakScanner.discover(timeout=8.0)
    doel = None
    for d in devices:
        naam = d.name or ""
        if naam.startswith("FS-") or naam.startswith("SYMK"):
            doel = d
            zeg(f"Gevonden: '{naam}' op {d.address}")
            break
    if not doel:
        zeg("Niets gevonden. Staat de band aan en is de app echt afgesloten?")
        return

    async with BleakClient(doel.address) as c:
        zeg("Verbonden.")
        zeg("--- karakteristieken ---")
        for s in c.services:
            for ch in s.characteristics:
                zeg(f"  {ch.uuid}  {','.join(ch.properties)}")

        for uuid, cb, naam in ((DATA, op_data, "data"), (CTRL, op_ctrl, "control"),
                               (TRAIN, op_train, "training"), (MACH, op_mach, "machine")):
            try:
                await c.start_notify(uuid, cb)
            except Exception as e:
                zeg(f"  (geen notify op {naam}: {e})")

        zeg("")
        try:
            await draai_test(c)
        finally:
            # De band moet stoppen, wat er ook misgaat onderweg.
            zeg("")
            zeg(">>> STOP")
            try:
                await c.write_gatt_char(CTRL, bytes([0x08, 0x01]), response=True)
            except Exception as e:
                zeg(f"    stop mislukte: {e}")
            await asyncio.sleep(10)

    zeg("")
    zeg("Klaar. Alles staat in loopband-diagnose.txt")


async def stuur(c, payload, wat):
    zeg("")
    zeg(f">>> {wat}   ({payload.hex(' ')})")
    await c.write_gatt_char(CTRL, payload, response=True)
    await asyncio.sleep(0.3)


async def draai_test(c):
    """Stuurt bekende waarden zodat we het uitgelezene ermee kunnen vergelijken."""
    await stuur(c, bytes([0x00]), "request control")
    await asyncio.sleep(2)

    zeg("")
    zeg("### FASE 1: stilstand, 8 seconden meten ###")
    await asyncio.sleep(8)

    await stuur(c, bytes([0x01]), "reset")
    await stuur(c, bytes([0x02, 0xC8, 0x00]), "snelheid 2.0 km/h")   # 200
    await stuur(c, bytes([0x07]), "start")
    zeg("")
    zeg("### FASE 2: verwacht 2.0 km/h, 20 seconden ###")
    await asyncio.sleep(20)

    await stuur(c, bytes([0x02, 0x90, 0x01]), "snelheid 4.0 km/h")   # 400
    zeg("")
    zeg("### FASE 3: verwacht 4.0 km/h, 20 seconden ###")
    await asyncio.sleep(20)

    await stuur(c, bytes([0x03, 0x1E, 0x00]), "helling 3%")          # 30
    zeg("")
    zeg("### FASE 4: verwacht 4.0 km/h en 3% helling, 25 seconden ###")
    await asyncio.sleep(25)

    await stuur(c, bytes([0x03, 0x00, 0x00]), "helling terug naar 0%")
    zeg("")
    zeg("### FASE 5: helling zakt terug, 20 seconden ###")
    await asyncio.sleep(20)
  
asyncio.run(main())  
