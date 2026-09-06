"""
TREADMILL SERVER - control your treadmill from your phone, with big buttons.

WHAT THIS IS:
  A small web server that runs on your LAPTOP and:
    - holds the Bluetooth connection to the treadmill;
    - reads the treadmill correctly (speed, incline, distance, time, calories);
    - serves an ACCESSIBLE web page with buttons that you open on your phone
      and add to your Home Screen.

  So you control the treadmill with screen-reader-friendly buttons, while the
  laptop does the Bluetooth work.

START (on the laptop):
  pip install quart bleak
  python tr600i_server.py

  The terminal then shows a line like:
     Open on your phone:  http://laptop.local:8000
  Open that in Safari on your phone (same Wi-Fi as the laptop!), then use the
  share menu -> 'Add to Home Screen' for an app-like button.

BUTTONS ON THE PAGE:
  Start (1 km/h) - Faster / Slower - Incline up / down - Stop
  Below that, tap the status area to hear what the treadmill is doing.

SAFETY:
  - Test with the belt EMPTY first.
  - 'Stop' is a deliberate stop, NOT your emergency brake. The physical STOP
    button and the safety key always work and are your real emergency stop.
  - This model goes up to 15% incline; asking for more has no effect.
"""

import asyncio
import socket
from bleak import BleakClient, BleakScanner
from quart import Quart, jsonify, render_template_string

# ---- Built-in settings ----
LOOPBAND_ADRES = "XX:XX:XX:XX:XX:XX"   # leave as-is to auto-detect
NAAM_HINTS = ("FS-", "SYMK")
POORT = 8000

# Limits and step sizes (adjust to taste)
SNELHEID_START = 0.8      # the speed the treadmill puts itself at on 'start'
SNELHEID_MIN = 0.8
SNELHEID_MAX = 22.0       # TR600i factory spec; lower it to taste
SNELHEID_STAP = 0.5       # km/h per press of faster/slower
HELLING_MIN = 0.0
HELLING_MAX = 15.0        # this model caps at 15%
HELLING_STAP = 1.0        # % per press
# Level the belt out when you stop, so you never step onto a forgotten incline.
HELLING_BIJ_STOP_NAAR_NUL = True
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

app = Quart(__name__)


class Toestand:
    """Shared state between the Bluetooth task and the web page."""
    def __init__(self):
        self.client = None
        self.verbonden = False
        self.lopend = False
        self.ingesteld_snelheid = 0.0
        self.ingesteld_helling = 0.0
        # Measured by the treadmill:
        self.snelheid = 0.0
        self.helling = 0.0
        self.afstand_m = 0
        self.tijd_s = 0
        self.calorieen = 0
        self.status = "connecting..."
        self.lock = asyncio.Lock()
        # The incline survives a power cycle, so adopt the measured value once.
        self.helling_overgenomen = False

S = Toestand()


def parse_treadmill_data(data: bytearray) -> dict:
    """Parse FTMS Treadmill Data. Field order follows the flags (little-endian).

    Bit 0 == 0 means: instantaneous speed PRESENT (that's how FTMS defines it).
    This treadmill sends TWO kinds of notification on 2ACD, alternating: the
    real 19-byte packet with flags 0x058c, and a 5-byte one with flags 0x2001
    where bit 0 IS set, so it carries no speed. Reading bytes 2-3 regardless
    made every other update report 0.0 km/h.
    """
    out = {}
    if len(data) < 2:
        return out
    flags = int.from_bytes(data[0:2], "little")
    i = 2
    # Instantaneous speed - only when bit 0 is clear.
    if not (flags & 1) and i + 2 <= len(data):
        out["snelheid"] = int.from_bytes(data[i:i+2], "little") / 100; i += 2
    if flags & (1 << 1) and i + 2 <= len(data):  # average speed
        i += 2
    if flags & (1 << 2) and i + 3 <= len(data):  # distance (3 bytes)
        out["afstand_m"] = int.from_bytes(data[i:i+3], "little"); i += 3
    if flags & (1 << 3) and i + 4 <= len(data):  # incline + ramp angle (2 bytes each)
        out["helling"] = int.from_bytes(data[i:i+2], "little", signed=True) / 10; i += 4
    if flags & (1 << 4) and i + 4 <= len(data):  # pos/neg elevation
        i += 4
    if flags & (1 << 5) and i + 1 <= len(data):  # pace
        i += 1
    if flags & (1 << 6) and i + 1 <= len(data):  # average pace
        i += 1
    if flags & (1 << 7) and i + 5 <= len(data):  # energy: total(2)+hour(2)+min(1)
        out["calorieen"] = int.from_bytes(data[i:i+2], "little"); i += 5
    if flags & (1 << 8) and i + 1 <= len(data):  # heart rate (we ignore it)
        i += 1
    if flags & (1 << 9) and i + 1 <= len(data):  # metabolic equivalent
        i += 1
    if flags & (1 << 10) and i + 2 <= len(data):  # elapsed time (s)
        out["tijd_s"] = int.from_bytes(data[i:i+2], "little"); i += 2
    return out


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

    # 1) Fixed address, if set and visible.
    if adres_ingevuld and LOOPBAND_ADRES.upper() in adressen:
        print("Configured address found.")
        return LOOPBAND_ADRES
    if adres_ingevuld:
        print("Configured address not seen; trying by name anyway...")

    # 2) Search by name (FitShow treadmills advertise as 'FS-...').
    kandidaten = [(adr, naam) for adr, naam in adressen.items()
                  if any(h.lower() in naam.lower() for h in NAAM_HINTS)]

    if len(kandidaten) == 1:
        adr, naam = kandidaten[0]
        print(f"Auto-detected: '{naam}' at {adr}.")
        if not adres_ingevuld:
            print("Tip: set this as LOOPBAND_ADRES near the top of the script")
            print("for a slightly faster connect next time.")
        return adr

    if len(kandidaten) > 1:
        print("\nMultiple possible treadmills found:")
        for i, (adr, naam) in enumerate(kandidaten, 1):
            print(f"  {i}. '{naam}'  ->  {adr}")
        print("\nPick one by setting its address as LOOPBAND_ADRES near the top")
        print("of the script, then start again.")
        return None

    # 3) Nothing found.
    print("\nNo FitShow treadmill found. Most common causes:")
    print("  - The FitShow app is still open on your phone and holds the")
    print("    connection. Close that app completely and try again.")
    print("  - The treadmill is off or asleep: switch it on and wait a moment.")
    print("  - Your treadmill isn't named 'FS-...'. Then set the address manually")
    print("    as LOOPBAND_ADRES near the top of the script (see the README).")
    return None


async def stuur(payload: bytes):
    """Send a command to the Control Point (using the connection lock)."""
    if not S.client or not S.verbonden:
        return False
    async with S.lock:
        try:
            await S.client.write_gatt_char(CONTROL_POINT_CHAR, payload, response=True)
            await asyncio.sleep(0.3)
            return True
        except Exception as e:
            print(f"Error while sending: {e}")
            return False


# ---- Commands translated to bytes ----
async def cmd_start():
    """Start the belt.

    The treadmill always starts at its own 0.8 km/h and discards any speed set
    beforehand, so we don't fight it: we report what it actually does and you
    adjust from there.
    """
    await stuur(bytes([OP_RESET]))
    await stuur(bytes([OP_START]))
    S.ingesteld_snelheid = SNELHEID_START
    S.lopend = True


def volgende_stap(huidig, richting):
    """Step onto the next multiple of SNELHEID_STAP instead of adding to it.

    The treadmill starts itself at 0.8 km/h; plain addition would then walk you
    through 1.3, 1.8, 2.3. Snapping to the grid gives 1.0, 1.5, 2.0 instead.
    """
    raster = huidig / SNELHEID_STAP
    import math
    n = math.floor(raster) + 1 if richting > 0 else math.ceil(raster) - 1
    return n * SNELHEID_STAP


async def cmd_snelheid(snelheid):
    snelheid = max(SNELHEID_MIN, min(SNELHEID_MAX, round(snelheid, 1)))
    v = int(round(snelheid * 100))
    await stuur(bytes([OP_SET_SPEED]) + v.to_bytes(2, "little"))
    S.ingesteld_snelheid = snelheid


async def cmd_helling(helling):
    helling = max(HELLING_MIN, min(HELLING_MAX, round(helling, 1)))
    v = int(round(helling * 10))
    await stuur(bytes([OP_SET_INCLINE]) + v.to_bytes(2, "little", signed=True))
    S.ingesteld_helling = helling


async def cmd_stop():
    """Stop the belt, levelling the incline first.

    Returns a bit of extra text for the spoken confirmation, or "" if the belt
    was already flat. Note this only applies to stopping from the app: if you
    use the physical STOP button or the safety key, the incline stays put.
    """
    extra = ""
    if HELLING_BIJ_STOP_NAAR_NUL and S.ingesteld_helling > HELLING_MIN:
        await stuur(bytes([OP_SET_INCLINE]) + (0).to_bytes(2, "little", signed=True))
        S.ingesteld_helling = 0.0
        extra = " Incline back to zero."
    await stuur(bytes([OP_STOP, 0x01]))
    S.lopend = False
    S.ingesteld_snelheid = 0.0
    return extra


# ---- Bluetooth background task: connect and read ----
async def bluetooth_taak():
    adres = await vind_adres()
    if not adres:
        S.status = "treadmill not found"
        return

    while True:
        try:
            print(f"Connecting to {adres} ...")
            async with BleakClient(adres) as client:
                S.client = client
                S.verbonden = True
                S.status = "connected, ready"
                S.helling_overgenomen = False   # re-adopt on every reconnect
                print("Connected.")

                def op_data(_, d):
                    p = parse_treadmill_data(d)
                    if "snelheid" in p:
                        S.snelheid = p["snelheid"]
                    if "helling" in p:
                        S.helling = p["helling"]
                        # The belt keeps its incline when switched off, so trust
                        # the machine over our own zero on the first reading.
                        if not S.helling_overgenomen:
                            S.ingesteld_helling = p["helling"]
                            S.helling_overgenomen = True
                    if "afstand_m" in p:
                        S.afstand_m = p["afstand_m"]
                    if "tijd_s" in p:
                        S.tijd_s = p["tijd_s"]
                    if "calorieen" in p:
                        S.calorieen = p["calorieen"]

                def op_status(_, d):
                    if len(d) >= 2:
                        codes = {0x01: "ready", 0x0d: "running",
                                 0x0e: "warming up", 0x0f: "cooling down"}
                        S.status = codes.get(d[1], f"status {d[1]}")
                        if d[1] in (0x01, 0x0f):
                            S.lopend = False

                def op_machine(_, d):
                    if d and d[0] == 0x02:
                        S.status = "stopped (button/key)"
                        S.lopend = False

                try:
                    await client.start_notify(TREADMILL_DATA_CHAR, op_data)
                except Exception as e:
                    print(f"(no treadmill-data notify: {e})")
                try:
                    await client.start_notify(TRAINING_STATUS_CHAR, op_status)
                except Exception:
                    pass
                try:
                    await client.start_notify(MACHINE_STATUS_CHAR, op_machine)
                except Exception:
                    pass

                await stuur(bytes([OP_REQUEST_CONTROL]))

                # Stay connected as long as the connection is alive.
                while client.is_connected:
                    await asyncio.sleep(1)

        except Exception as e:
            print(f"Connection lost or failed: {e}")
        finally:
            S.verbonden = False
            S.client = None
            S.status = "connection lost, retrying..."
        # Wait a bit and try to reconnect.
        await asyncio.sleep(3)


@app.before_serving
async def start_bluetooth():
    app.add_background_task(bluetooth_taak)


# ---- Web page ----
PAGINA = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Treadmill">
<title>Treadmill</title>
<style>
  :root { --pad: 18px; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, system-ui, sans-serif;
    margin: 0; padding: var(--pad);
    background: #111; color: #fff; font-size: 20px;
  }
  h1 { font-size: 24px; margin: 0 0 12px; }
  #status {
    background: #1d1d1f; border: 2px solid #333; border-radius: 12px;
    padding: 16px; margin-bottom: 18px; line-height: 1.5;
    color: #fff; font-size: 18px; font-family: inherit;
  }
  #status:focus { outline: 4px solid #0a84ff; outline-offset: 2px; }
  .knoprij { display: flex; gap: 12px; margin-bottom: 12px; }
  button {
    flex: 1; min-height: 72px; font-size: 22px; font-weight: 600;
    color: #fff; background: #2c2c2e; border: 2px solid #48484a;
    border-radius: 14px; padding: 14px; cursor: pointer;
  }
  button:active { background: #3a3a3c; }
  button:focus { outline: 4px solid #0a84ff; outline-offset: 2px; }
  .start { background: #1f6f43; border-color: #2ea866; }
  .stop  { background: #7a1f1f; border-color: #c0392b; }
  .groot { font-size: 26px; }
  .label { font-size: 16px; color: #aaa; margin: 18px 0 6px; }
</style>
</head>
<body>
  <h1>Treadmill</h1>

  <!-- Status box: does NOT auto-read. You navigate to it yourself (it's a
       button, so VoiceOver lands on it easily) when you want to hear the
       state. role=status without aria-live won't read out on its own. -->
  <button id="status" aria-label="Current state, double-tap to read aloud"
          onclick="ververs(true)"
          style="display:block;width:100%;text-align:left;">
    Connecting to the treadmill...
  </button>

  <!-- Invisible box that IS read out immediately, but only holds a short
       confirmation after a button press. -->
  <div id="melding" role="status" aria-live="assertive" aria-atomic="true"
       style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;"></div>

  <div class="knoprij">
    <button class="start groot" onclick="doe('start')"
            aria-label="Start the treadmill at 1 kilometer per hour">Start</button>
    <button class="stop groot" onclick="doe('stop')"
            aria-label="Stop the treadmill">Stop</button>
  </div>

  <div class="label">Speed</div>
  <div class="knoprij">
    <button onclick="doe('langzamer')" aria-label="Slower, half a kilometer per hour less">Slower &minus;</button>
    <button onclick="doe('sneller')" aria-label="Faster, half a kilometer per hour more">Faster +</button>
  </div>

  <div class="label">Incline</div>
  <div class="knoprij">
    <button onclick="doe('helling_omlaag')" aria-label="Incline down, one percent less">Incline &minus;</button>
    <button onclick="doe('helling_omhoog')" aria-label="Incline up, one percent more">Incline +</button>
  </div>

<script>
  // Update the status box WITHOUT reading it aloud. If you call this with
  // aloud=true (after tapping the status box), we briefly put the text in the
  // announcement box so VoiceOver reads it once.
  async function ververs(aloud) {
    try {
      const r = await fetch('/stand');
      const d = await r.json();
      let t;
      if (!d.verbonden) {
        t = 'Not connected. ' + d.status + '.';
      } else if (!d.lopend && d.ingesteld_snelheid === 0) {
        t = 'Idle. Ready to start. Status: ' + d.status + '.';
      } else {
        t = 'Speed ' + d.ingesteld_snelheid.toFixed(1) + ' kilometers per hour. '
          + 'Incline ' + d.ingesteld_helling.toFixed(0) + ' percent. '
          + 'Distance ' + d.afstand_m + ' meters. '
          + 'Time ' + Math.floor(d.tijd_s/60) + ' minutes ' + (d.tijd_s%60) + ' seconds. '
          + d.calorieen + ' calories.';
      }
      document.getElementById('status').textContent = t;
      if (aloud) meld(t);  // only read out when you asked for it
    } catch (e) {
      document.getElementById('status').textContent = 'No contact with the laptop server.';
    }
  }

  // Put a short text in the invisible announcement box. VoiceOver reads it
  // once. We clear it first so the same text is re-announced if you repeat
  // the same action.
  function meld(tekst) {
    const m = document.getElementById('melding');
    m.textContent = '';
    setTimeout(() => { m.textContent = tekst; }, 50);
  }

  // Send a command. The short confirmation goes to the announcement box (read
  // out); the status box is updated silently.
  async function doe(actie) {
    try {
      const r = await fetch('/cmd/' + actie, { method: 'POST' });
      const d = await r.json();
      if (d.melding) meld(d.melding);
      setTimeout(() => ververs(false), 700);
    } catch (e) {
      meld('Command could not be sent.');
    }
  }

  // Update the state in the background silently (no reading aloud), so the
  // text is correct the moment you navigate to it yourself.
  setInterval(() => ververs(false), 3000);
  ververs(false);
</script>
</body>
</html>"""


@app.route("/")
async def index():
    return await render_template_string(PAGINA)


@app.route("/stand")
async def stand():
    return jsonify({
        "verbonden": S.verbonden,
        "lopend": S.lopend,
        "status": S.status,
        "ingesteld_snelheid": S.ingesteld_snelheid,
        "ingesteld_helling": S.ingesteld_helling,
        "snelheid": S.snelheid,
        "helling": S.helling,
        "afstand_m": S.afstand_m,
        "tijd_s": S.tijd_s,
        "calorieen": S.calorieen,
    })


@app.route("/cmd/<actie>", methods=["POST"])
async def cmd(actie):
    if not S.verbonden:
        return jsonify({"ok": False, "melding": "Not connected to the treadmill."})

    melding = ""
    if actie == "start":
        await cmd_start()
        melding = f"Started at {SNELHEID_START:.1f} kilometers per hour."
    elif actie == "stop":
        melding = "Stopped." + await cmd_stop()
    elif actie == "sneller":
        await cmd_snelheid(volgende_stap(S.ingesteld_snelheid, +1))
        melding = f"Speed {S.ingesteld_snelheid:.1f} kilometers per hour."
    elif actie == "langzamer":
        await cmd_snelheid(volgende_stap(S.ingesteld_snelheid, -1))
        melding = f"Speed {S.ingesteld_snelheid:.1f} kilometers per hour."
    elif actie == "helling_omhoog":
        await cmd_helling(S.ingesteld_helling + HELLING_STAP)
        melding = f"Incline {S.ingesteld_helling:.0f} percent."
        if S.ingesteld_helling >= HELLING_MAX:
            melding += " This is the maximum."
    elif actie == "helling_omlaag":
        await cmd_helling(S.ingesteld_helling - HELLING_STAP)
        melding = f"Incline {S.ingesteld_helling:.0f} percent."
    else:
        return jsonify({"ok": False, "melding": "Unknown command."})

    return jsonify({"ok": True, "melding": melding})


def mijn_ip():
    """Find the local IP address so we can show the right URL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main():
    ip = mijn_ip()
    print("=" * 56)
    print("  Treadmill server started.")
    print(f"  Open on your phone (same Wi-Fi):  http://{ip}:{POORT}")
    print(f"  Or try the laptop name:           http://<your-laptop-name>.local:{POORT}")
    print("  In Safari -> share menu -> 'Add to Home Screen'.")
    print("  Stop: press Ctrl+C in this window.")
    print("=" * 56)
    app.run(host="0.0.0.0", port=POORT)


if __name__ == "__main__":
    main()
