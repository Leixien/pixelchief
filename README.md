# BasePilot

> Fork of [Mikyy85/coc-bot](https://github.com/Mikyy85/coc-bot) (BasePilot, MIT). The Python
> sources here were reconstructed from the released bytecode, so some logic was lost in
> decompilation and is being repaired commit by commit — expect differences from upstream.

**Autopilot for your Clash of Clans base.** BasePilot farms, upgrades, and knows when
to do nothing — it runs unattended until your village genuinely has nothing left to
start, then waits for a builder to free up and gets back to work.

Desktop app for **Clash of Clans on Google Play Games (Windows)** or Android via
ADB from Windows, Linux, or macOS. It plays the
game the way a person does: screen capture, computer vision, and clicks. No memory
reading, no packet manipulation, no modified client.

**[Download the latest release](../../releases/latest)** — a single `BasePilot.exe`
with the OCR engine bundled in, so there is nothing to install. This repository holds
the full source; see [Running from source](#running-from-source) to build it yourself.

![BasePilot running beside Clash of Clans: the Run page shows Maxer mode with "Run until
maxed" enabled, and the Live Status panel reports IDLING with 0/6 builders free and both
storages full](docs/basepilot-screenshot.png)

*BasePilot idling on purpose: storages are capped and every builder is busy, so it holds
position and rechecks instead of raiding for loot that would overflow.*

---

## What it does

**Farming.** Finds matches, deploys your army (Valkyries, Sneaky Goblins, Super
Minions, or Edrags), collects loot, returns home, and recovers on its own from popups,
disconnects, and stray screens. Builder Base farming included. See
[Army setup](#army-setup) for what to bring.

**Auto upgrade (beta).** Reads the builder menu with OCR and spends your loot:

- **Maxer** — starts an affordable upgrade and never touches your Town Hall. Priciest
  first by default, since a farmed account is builder-limited rather than loot-limited;
  switch to cheapest first in *Settings → Upgrade order* to spread builders across more
  jobs. Dark elixir upgrades (heroes) always get first claim either way.
- **Rusher** — takes the Town Hall as soon as it's affordable.
- **Dry run** — logs what it *would* start and clicks nothing. Good first setting.

**Run until maxed.** No time limit. Farm → spend → and when storages are full with
every builder busy, BasePilot **idles** instead of raiding for loot that would
overflow, rechecking every few minutes and resuming the moment something frees up.
It only stops when you tell it to.

**Wall upgrades.** Batch-buys walls when loot passes a threshold you set, elixir first,
keeping enough gold for match entry fees.

**Loot tracking.** Every raid's gold, elixir, and dark elixir gains are read straight
off the HUD and accumulated into a session total plus a **loot-per-hour rate**, so you
can see what an army or strategy is actually earning you instead of guessing. Readings
require agreement across consecutive frames and are sanity-checked against what a
single raid can plausibly yield, so a bad OCR frame can't inflate your numbers. (Note
that a capped storage banks nothing — the rate reflects real gains, not raid count.)

**Live status.** Current state, free builders, laboratory, and storage levels at a
glance, alongside the loot readout.

Works at **any Town Hall level** — detection reads the game's own UI signals (builder
chip, lab chip, storage indicators) rather than hardcoded per-TH values.

Not automated yet: starting laboratory research and Pet House upgrades. BasePilot
tracks the lab and tells you when it's idle, but you start those two yourself.

## Safety rails

Automation that spends resources has to be careful, so BasePilot:

- Never confirms a purchase whose cost shows red (unaffordable → gem-spend risk).
- Requires the screen to **name the building it picked** before any purchase click, so
  a mis-aimed click can't buy the wrong thing.
- Verifies every upgrade actually started by checking the builder counter afterward.
- Escapes unknown dialogs via their close button or empty ground — never a blind "OK".
- Keeps a gold buffer so matchmaking entry fees are never spent away.
- Screenshots anything it couldn't verify to `%LOCALAPPDATA%\BasePilot\debug\` and
  benches that upgrade instead of retrying blindly.

## Requirements

- Windows 10/11 for native Google Play Games control, or Windows/Linux/macOS for ADB
- Clash of Clans running in **Google Play Games on PC** or on an ADB-connected Android device
- The game rendering at **16:9** or 16:10

**Ultrawide / 21:9 monitors:** Google Play Games locks the game's aspect ratio to your
display resolution at launch. Use *Settings → Switch display to 16:9*, fully close and
reopen Clash, then *Restore my display* — the running game keeps 16:9.

## Getting started

1. Download `BasePilot.exe` from [Releases](../../releases/latest) and run it (no
   installer; settings live in `%LOCALAPPDATA%\BasePilot`). The exe is unsigned, so
   Windows SmartScreen warns on first launch — *More info → Run anyway*.
2. Open the game, then press **Test** on the Settings page to confirm BasePilot can see
   it. Use **Auto-detect** or pick the window manually if needed.
3. On the Run page, choose your army ([what to bring](#army-setup)), set
   **Auto upgrade → Dry run** for the first session, and press **Start**. Watch the Logs page
   to see what it would do.
4. Happy with its choices? Switch to **Maxer**, enable **Run until maxed**, and set
   *Settings → Reserve builders* (use 0 if your walls are maxed).

Command line, for scheduled or overnight runs:

```
BasePilot.exe --autostart --minutes 0 --walls --upgrades maxer
```

`--minutes 0` means run until maxed. `--upgrades off|dry|maxer|rusher`.

## Army setup

![Saved Recipes showing Army 1: 42 Valkyries, 11 Earthquake spells, and 1 Log Launcher, with
Queen, King, Warden, and Royal Champion and their pets](docs/army-valkyrie.png)

**42 Valkyries · 11 Earthquake spells · 1 Log Launcher**, plus your heroes and pets — 336/352
housing and a full 11/11 spell bar.

The 11 Earthquakes aren't arbitrary. BasePilot places exactly 11 earthquake points per raid, so
a full spell bar means every one of them lands a spell.

Three things to get right before you press Start:

- **Be on the Home Village.** Switch there yourself, or pick *Home Village* in the app and let
  the bot switch for you.
- **Use the default deployment bar layout.** Two rows is fine. BasePilot finds troops by
  matching their icons in that bar, so a customised layout can hide them.
- **Keep this army at the top of your Saved Recipes.** If Valkyries aren't already in your
  deploy bar, BasePilot opens Saved Recipes and clicks **Use** next to the Valkyrie row — but it
  only looks for that button close to the row it matched, so a recipe further down the list
  scrolls out of range and army loading fails.

If the troop you picked on the Run page isn't in your army, the raid aborts immediately and the
log reads `Troop <name> not found!`.

Sneaky Goblins and Super Minions deploy the same way. Edrags need at least 12. Full deploy
mechanics — drag patterns, earthquake placement modes, hero order — are in
[docs/armies.md](docs/armies.md).

## Running from source

Python 3.12+ in a virtual environment:

```
python -m pip install -r requirements.txt
python main.py
```

OCR needs a Tesseract 5 install. For development, BasePilot falls back to
`C:\Program Files\Tesseract-OCR\tesseract.exe`, so a
[UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) is enough — or point
`TESSERACT_CMD` at the executable you prefer. On Linux/macOS, install Tesseract
and its English language data using your OS package manager; BasePilot also
looks for `tesseract` on PATH. An explicit `TESSDATA_PREFIX` is preserved.

To build the one-file exe, copy that Tesseract install (`tesseract.exe`, its DLLs, and
`tessdata/`) into `tesseract_bundle/` and run:

```
pyinstaller BasePilot.spec
```

`tesseract_bundle/` is gitignored to keep the repo light — it is ~40 MB of Apache-2.0
binaries. The release workflow in `.github/workflows/release.yml` recreates it on a
Windows runner and publishes the exe automatically on every `v*` tag.

## Running with ADB

The bot uses `app.services.adb.AdbService` for Android screenshots and input on
Windows, Linux, and macOS. ADB is the default on Linux/macOS; Windows keeps native
window control unless `--adb` or `--serial` is supplied. The game runs on
an Android device or an ADB-accessible emulator; BasePilot runs on the computer.

Use Python 3.12+ and install [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
for your computer's OS. Make `adb` available on PATH, or pass its executable path
with `AdbService(adb='/path/to/adb', serial='SERIAL')` (`adb.exe` on Windows).
Enable USB debugging on the Android device, connect it, unlock it, and approve
the computer's debugging authorization prompt. For connection troubleshooting,
see the [ADB documentation](https://developer.android.com/tools/adb).

In a separate virtual environment, the standalone service only needs these
existing project dependencies:

```sh
python -m pip install "numpy>=2.2" "opencv-python>=4.12"
```

For the GUI and bot, install the full `requirements.txt` as shown above;
`pywin32` is installed only on Windows. Nothing is installed automatically.

Manual connection check (this invokes ADB and may start its local server):

```sh
adb devices
```

Use a serial whose state is `device`. `unauthorized` requires authorization on
the device; `offline` requires fixing the connection. The service requires an
explicit serial when more than one device is listed and never switches to a
different device after a failure.

Start the GUI with the chosen serial:

```sh
python main.py --adb --serial SERIAL
```

Without `--serial`, the first connection requires exactly one listed device,
which stays selected until the process exits. The GUI can open without a device.
In **Settings → Android device (ADB)**, **Test capture** checks the screenshot in
the background and shows the selected serial and dimensions. Start checks the
connection, landscape aspect, and held-drag support before sending game input.
To change devices, restart with another serial. Monitor/display controls are
available only in native Windows mode.

Manual screenshot check, with `SERIAL` replaced by your device's serial:

```sh
python -c "from app.services.adb import AdbService; print(AdbService('SERIAL').screenshot().shape)"
```

The result is `(height, width, 3)`, with OpenCV BGR channels. The following Python
example **sends touch input** to the selected device; use it only with a suitable
screen open:

```python
from app.services.adb import AdbService

device = AdbService('SERIAL')
device.tap(100, 200)
device.swipe(100, 400, 100, 200, duration_ms=500)
```

Coordinates are non-negative integer pixels in the captured device screen,
not desktop coordinates. Keep them inside the current screenshot dimensions.
Swipe duration is a positive integer in milliseconds. Each swipe presses and
releases independently; it does not preserve a held touch across multiple calls.
Commands have a configurable timeout (`timeout=10.0`, in seconds); connection,
command, and screenshot failures raise `RuntimeError`, while invalid coordinates
or duration raise `ValueError`.

The optional simulated check uses the full Python requirements above, needs no
ADB installation or connected device, and
does not send commands or write screenshots. Run it manually without Python's
`-O` option, so its assertions remain enabled:

```sh
python -m app.services.adb --check
```

Expected output: `ADB simulated check passed.` This checks command construction,
serial routing, screenshot decoding, input validation, and connection failures.
It does not establish device compatibility or performance.

The bot uses `input motionevent DOWN/MOVE/UP` for held drags and refuses to start
if the device does not advertise this command. Stop/error cleanup attempts to
release held touches on the same device. A disconnected device cannot receive
the release until connectivity is restored. ADB input latency and gesture
behavior must be checked on your device before relying on unattended operation;
the simulated check does not validate those properties.
The current recognition code accepts approximately 16:9 or 16:10; other Android
aspect ratios and game layouts still need coordinate/template validation.

## License

MIT — see [LICENSE](LICENSE). Tesseract, bundled into the released exe, ships under the
Apache 2.0 license.

## Disclaimer

Automating Clash of Clans **violates Supercell's Terms of Service and can get your
account banned.** BasePilot is published for educational purposes — it's a real-world
exercise in computer vision, OCR, and UI automation against an animated, adversarial
target. Use it on an account you're willing to lose, or don't use it at all. No
warranty; you accept all risk.

Not affiliated with, endorsed by, or associated with Supercell. Clash of Clans is a
trademark of Supercell Oy.
