# Native iOS app (no laptop, no server)

This talks to the treadmill **directly over Bluetooth** from the iPhone, using the
same FTMS protocol documented in [`docs/PROTOCOL.md`](../docs/PROTOCOL.md). The
Python bridge is not involved: no Wi-Fi, no laptop, nothing to start.

Same warning as the rest of this project: **the physical STOP button and the safety
key are your emergency stop, not this app.** Test with the belt empty first.

## What's in here

| File | What it does |
|---|---|
| `project.yml` | XcodeGen spec. The `.xcodeproj` is generated from this, not committed. |
| `Sources/FTMS.swift` | Bluetooth UUIDs, opcodes, limits and step sizes. |
| `Sources/Treadmill.swift` | The connection, the parser, and the commands. |
| `Sources/TreadmillIntents.swift` | App Intents, so Siri and Shortcuts can drive it. |
| `Sources/ContentView.swift` | Large buttons, VoiceOver announcements. |

## Building without a Mac

Push to GitHub and the workflow in `.github/workflows/ios.yml` builds an **unsigned**
`.ipa` on a free macOS runner (free for public repositories). Download it from the
run's artifacts, then sign and install it on Windows with **Sideloadly**, **AltStore**
or **SideStore** using a normal free Apple ID.

Free Apple ID rules, none of which this project can change: certificates last
**7 days**, you can keep **3 sideloaded apps** at a time, and roughly 10 new app IDs
per week. SideStore refreshes on-device so your laptop does not have to be running.

With a Mac, skip all of that: `brew install xcodegen && cd ios && xcodegen generate`,
open `Loopband.xcodeproj`, set your Apple ID under Signing, and press Run.

## Siri, and the entitlement catch

Direct voice phrases (`Sneller in Loopband`) need the `com.apple.developer.siri`
entitlement, which the free tier does not grant. Without it the phrases silently
do nothing in Siri — but the intents **still appear in the Shortcuts app**.

So the reliable route is the same one the web version uses:

1. Shortcuts app → new shortcut → add the action **Sneller** (under Loopband).
2. Name the shortcut `Sneller`.
3. Press the assistant button on your headphones and say "Sneller".

Repeat for Langzamer, Steiler, Vlakker, Start, Stop and Status. For
`Snelheid instellen` and `Helling instellen`, leave the parameter empty and Siri
will ask "Welke snelheid?" — then you just say a number.

## Known rough edges

- Background Bluetooth is the fragile part. `bluetooth-central` plus state
  restoration is set up, but if an intent fires after the app has been killed,
  reconnecting can take a few seconds before the command lands.
- The treadmill is remembered by its peripheral identifier after the first
  connection, so only the very first run needs a scan.
- Speed and incline are clamped to the same limits as `tr600i_server.py`.
