# Treadmill Bluetooth (FTMS) protocol — FitShow FS-BT-C1

Reverse-engineered from a measurement session. This treadmill (sold in NL as the
VirtuFit TR600i, FitShow app, advertises as `FS-...`) follows the standard **FTMS**
(Fitness Machine Service) spec properly. You do **not** need a vendor-specific
channel: all data comes over the standard FTMS characteristics.

> **Important for other treadmills:** the Bluetooth control isn't really in the
> "VirtuFit TR600i" itself, but in a **FitShow FS-BT-C1** module that's built into
> many treadmills from different brands. So this protocol likely applies to *any*
> treadmill using this (or a related) FitShow module — not just the TR600i.

## Module identification (read from Device Information)

| Field            | Value        | Meaning |
|------------------|--------------|---------|
| Manufacturer     | `FITSHOW`    | maker of the control module |
| Model number     | `FS-BT-C1`   | the Bluetooth controller, not the treadmill model |
| Firmware revision| `V2.6.3`     | module firmware |
| Hardware revision| `1.0`        | |
| Software revision| `1.4.2`      | |
| Device name      | `FS-XXXXXX`  | advertises as `FS-` + hex |

(Treadmill factory specs, TR600i: speed up to 22 km/h, incline up to 15%,
belt 150x51 cm, max user weight 150 kg.)

## Control — Control Point (`00002ad9`, write + indicate)

First **request control**, then you may send commands. Each command gets an
indication back of the form `80 <opcode> <result>`, where `01` = success.

| Action          | Bytes (hex)                  | Notes |
|-----------------|------------------------------|-------|
| Request control | `00`                         | once, before the rest |
| Reset           | `01`                         | back to start |
| Set speed       | `02` + `<km/h x100, 2 bytes LE>` | e.g. 5.0 km/h -> `500` = `0x01F4` -> `02 F4 01` |
| Set incline     | `03` + `<% x10, 2 bytes LE, signed>` | e.g. 5.0% -> `50` = `0x0032` -> `03 32 00` |
| Start           | `07`                         | belt starts |
| Stop            | `08 01`                      | deliberate stop (NOT emergency) |

**Note on incline:** FTMS works in percent with 0.1% steps, so the value is
*percent x 10*. Ask for more than 15% (value 150) and the treadmill replies "OK"
but stays at 15% — nothing changes and it won't beep. That's not an error; it's
just this treadmill's ceiling.

## Reading — Treadmill Data (`00002acd`, notify)

Each message starts with 2 **flag bytes** (little-endian) that say which fields
follow. On this model the flags are consistently `0x058c`. Fields then follow in a
fixed order. Important: in FTMS, flag bit 0 == 0 means *instantaneous speed is
present* (so it's always there).

Field order as this treadmill sends them (flags `0x058c`):

| Field                  | Size    | Conversion           | Example |
|------------------------|---------|----------------------|---------|
| Instantaneous speed    | 2 bytes | /100 -> km/h         | `8403` -> 900 -> 9.0 km/h |
| Distance               | 3 bytes | meters               | |
| Incline (%)            | 2 bytes | /10 (signed) -> %    | `9600` -> 150 -> 15.0% |
| Ramp angle             | 2 bytes | /10 (signed) -> deg  | usually 0 |
| Positive elevation     | 2 bytes | /10                  | |
| Negative elevation     | 2 bytes | /10                  | |
| Energy total (kcal)    | 2 bytes | kcal                 | |
| Energy per hour        | 2 bytes | `0xFFFF` = unknown   | not computed |
| Energy per minute      | 1 byte  | `0xFF` = unknown     | not computed |
| Heart rate             | 1 byte  | bpm                  | unreliable without a chest strap |
| Elapsed time           | 2 bytes | seconds              | |

Example (running at 9 km/h, 19 seconds in):
```
8c05 8403 110000 0000 0000 0000 0000 0100 ffffff 1300
flags spd  dist   incl ramp posE negE kcal ...    time
```
-> speed 9.0 km/h, incline 0.0%, energy field 19, time 19 s.

## Other channels present (not needed)

The treadmill also exposes a vendor service `fff0` with characteristic `fff1`
(notify) that sends its own parallel summary. For full control + reading this is
**not needed** — the standard FTMS channel already provides everything. There are
also standard info channels (device name, manufacturer) and a heart-rate service.

## Status messages

- **Training Status** `00002ad3`: `010e` = warming up, `010d` = running,
  `0101` = ready/idle, `010f` = cooling down.
- **Machine Status** `00002ada`: `04` = started/resumed, `0201` = stopped by user
  (e.g. safety key / STOP button).

---
*Reverse-engineered from a personal measurement session with the belt empty.
Intended as reference and as a starting point for other FitShow/FTMS treadmills.*
