"""Vervolgtest: wordt een snelheid die vóór 'start' is gezet genegeerd?"""

import asyncio, time
from bleak import BleakClient, BleakScanner

CTRL  = "00002ad9-0000-1000-8000-00805f9b34fb"
DATA  = "00002acd-0000-1000-8000-00805f9b34fb"
TRAIN = "00002ad3-0000-1000-8000-00805f9b34fb"

def op_data(_, d):
    b = bytes(d)
    if len(b) < 19:
        return                      # het 5-byte vervolgpakket slaan we over
    snelheid = int.from_bytes(b[2:4], "little") / 100
    print(f"[{time.strftime('%H:%M:%S')}] gemeten {snelheid:.2f} km/h")

def op_train(_, d):
    codes = {0x01: "idle", 0x0d: "loopt", 0x0e: "opwarmen", 0x0f: "afkoelen"}
    b = bytes(d)
    if len(b) >= 2:
        print(f"[{time.strftime('%H:%M:%S')}] status: {codes.get(b[1], hex(b[1]))}")

async def main():
    devices = await BleakScanner.discover(timeout=8.0)
    doel = next((d for d in devices if (d.name or "").startswith(("FS-", "SYMK"))), None)
    if not doel:
        print("Loopband niet gevonden.")
        return

    async with BleakClient(doel.address) as c:
        await c.start_notify(DATA, op_data)
        await c.start_notify(TRAIN, op_train)
        await c.write_gatt_char(CTRL, bytes([0x00]), response=True)
        await asyncio.sleep(1)

        try:
            print("\n### reset, dan direct start (GEEN snelheid vooraf) ###")
            await c.write_gatt_char(CTRL, bytes([0x01]), response=True)
            await asyncio.sleep(0.3)
            await c.write_gatt_char(CTRL, bytes([0x07]), response=True)
            await asyncio.sleep(0.3)

            print("### meteen snelheid 3.0 zetten ###")
            await c.write_gatt_char(CTRL, bytes([0x02, 0x2C, 0x01]), response=True)
            print("### 18 seconden kijken of hij 3.0 haalt ###")
            await asyncio.sleep(18)

            print("\n### nogmaals 3.0 sturen, nu terwijl hij loopt ###")
            await c.write_gatt_char(CTRL, bytes([0x02, 0x2C, 0x01]), response=True)
            await asyncio.sleep(12)
        finally:
            print("\n### stop ###")
            await c.write_gatt_char(CTRL, bytes([0x08, 0x01]), response=True)
            await asyncio.sleep(10)

asyncio.run(main())
