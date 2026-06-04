# Accessible treadmill control (FitShow / FTMS)

Control a FitShow-based treadmill from your phone with **big, screen-reader-friendly
buttons**, instead of the inaccessible FitShow app or a flat touch panel.

A small server runs on your laptop (it holds the Bluetooth connection and reads the
treadmill), and serves a simple web page you open on your phone — works great with
VoiceOver and as a Home Screen shortcut on iOS.

Built for and tested on a **VirtuFit TR600i** (sold in NL), which uses a
**FitShow FS-BT-C1** Bluetooth module. The same approach very likely works for other
treadmills using a FitShow module and the standard FTMS protocol.

> ⚠️ **What you see is what you get.** This is a personal hobby project, shared as-is,
> with no guarantees. It worked on my treadmill; yours may differ. **Always test with
> the belt empty first, and keep the physical STOP button / safety key within reach —
> that is your real emergency stop, not the "Stop" button in this app.** Use at your
> own risk.

## Why this exists

I'm blind. My treadmill has a flat panel with recessed buttons I can't feel, and the
FitShow app isn't usable with VoiceOver. So I reverse-engineered the Bluetooth protocol
and built an accessible way to drive it myself — no sighted help required.

## What's here

- `tr600i_server.py` — the main program: laptop server + accessible web page.
- `tr600i_info.py` — reads the module's model/firmware info (handy to confirm yours).
- `tr600i_combi.py` — logging tool used to reverse-engineer the protocol (optional).
- `docs/PROTOCOL.md` — what I found out about how the treadmill talks over Bluetooth.

## Setup

On the laptop (needs Python 3):

```
pip install quart bleak
python tr600i_server.py
```

The terminal prints an address, e.g. `http://laptop.local:8000` (or an IP address).
Open that in **Safari** on your phone (same Wi-Fi), then Share → **Add to Home Screen**
for an app-like button. Using the laptop's name (`laptop.local`) is nicer than the IP,
because the IP can change but the name doesn't.

## Configure for your treadmill (usually optional)

By default the server **scans and auto-detects** a FitShow treadmill (they advertise
as `FS-...`). If exactly one is found, it just connects — you don't have to configure
anything. If it finds several (e.g. a neighbour also has one), it lists them and asks
you to pick.

To pin a specific treadmill (slightly faster connect, or when several are nearby),
set its Bluetooth address near the top of `tr600i_server.py`:

```python
LOOPBAND_ADRES = "XX:XX:XX:XX:XX:XX"   # leave as-is to auto-detect
```

Don't know the address? Just run the server and let it auto-detect, or run
`tr600i_info.py`, or use any BLE scanner app. Speed/incline limits and step sizes are
also adjustable at the top of the file.

## Buttons

Start (1 km/h) · Slower / Faster · Incline down / up · Stop. Tap the status area to hear
the current speed, incline, distance, time and calories (it doesn't read out on its own).

## Related work

- [tyge68/fitshow-treadmill](https://github.com/tyge68/fitshow-treadmill) — browser app
  for a FitShow F31 (Web Bluetooth; note: doesn't work on iOS).
- [samsonovss/ESPHome-Treadmill-FTMS](https://github.com/samsonovss/ESPHome-Treadmill-FTMS)
  — replaces the treadmill's controller with an ESP32 + ESPHome.

This project's angle is different: **leave the treadmill untouched, add an accessible
iPhone control via a laptop bridge.**

## License

MIT — see [LICENSE](LICENSE).
