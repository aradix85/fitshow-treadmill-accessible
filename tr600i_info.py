"""
TREADMILL INFO - read model, manufacturer and firmware from the treadmill.

Connects briefly, reads the standard 'Device Information' characteristics,
and disconnects. The treadmill does NOT need to be running. The FitShow app
must be closed.

START:
  python tr600i_info.py
"""

import asyncio
from bleak import BleakClient, BleakScanner

LOOPBAND_ADRES = "XX:XX:XX:XX:XX:XX"   # leave as-is to auto-detect
NAAM_HINTS = ("FS-", "SYMK")

# Standard Device Information characteristics (UUID -> meaning)
INFO_KANALEN = {
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model number",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial number",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware revision",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software revision",
    "00002a23-0000-1000-8000-00805f9b34fb": "System ID",
    "00002a50-0000-1000-8000-00805f9b34fb": "PnP ID",
    "00002a00-0000-1000-8000-00805f9b34fb": "Device name",
    "00002a51-0000-1000-8000-00805f9b34fb": "IEEE regulatory",
    "00002a46-0000-1000-8000-00805f9b34fb": "New alert",
}


async def vind_adres():
    """Find the treadmill automatically.

    Order:
      1) Is a valid fixed address set and do we see it? -> use it.
      2) Otherwise scan and look for a FitShow treadmill by name (FS-...).
         - exactly one found -> use it automatically.
         - several found     -> list them and explain how to choose.
         - none found        -> friendly explanation of the most common cause.
    Returns the address, or None if nothing usable was found.
    """
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


def leesbaar(rauw: bytes) -> str:
    # Try text; fall back to hex.
    try:
        tekst = rauw.decode("utf-8").strip("\x00").strip()
        if tekst and all(32 <= ord(c) < 127 for c in tekst):
            return f'"{tekst}"'
    except Exception:
        pass
    return f"(hex) {rauw.hex()}"


async def main():
    adres = await vind_adres()
    if not adres:
        return
    print(f"\nConnecting to {adres} ...")
    async with BleakClient(adres) as client:
        print("Connected. Reading info characteristics:\n")
        aanwezig = {c.uuid.lower() for s in client.services for c in s.characteristics}
        for uuid, naam in INFO_KANALEN.items():
            if uuid in aanwezig:
                try:
                    waarde = await client.read_gatt_char(uuid)
                    print(f"  {naam:18s}: {leesbaar(bytes(waarde))}")
                except Exception as e:
                    print(f"  {naam:18s}: could not read ({e})")
    print("\nDone. Share these lines to identify model + firmware.")


if __name__ == "__main__":
    asyncio.run(main())
