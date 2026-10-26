# Sim Racing HUD

iRacing overlays in one app: a replica **dash**, a **side indicator**, a **pit-lane relative** and a
**team pit board**. They share one iRacing connection, one tray icon, one settings window and one
auto-start.

## Install
1. Go to **[Releases](https://github.com/90kacoupe/iRacing_HUD/releases/latest)** and download
   `SimRacingHUD-Setup-x.y.z.exe`. No Python or GitHub account needed.
2. Run it. Windows may say *"Windows protected your PC"* the first time, because the app isn't
   signed by a big publisher: click **More info → Run anyway**.
3. Look for the icon in the tray (bottom right of the taskbar). **Double-click it for Settings.**
   The overlays start in the middle of the screen: press **Ctrl+Shift+E** (layout mode) to drag
   them where you want.

There's also a **Sim Racing HUD (demo)** entry in the Start menu that shows everything with
simulated data, no iRacing needed.

## Updates
The HUD checks for a new version now and then. When there is one, a notification appears
(only when you're **not on track**, never mid-race). Click it to see what's new and choose
**Update now**, **Remind me later** or **Skip this version**. Updating keeps all your settings.
You can also use **Check for updates** in the tray menu, or turn the checks off in Settings → General.

## Running from the source code instead
1. Double-click **`setup.bat`**. It:
   - closes the old separate dash and side indicator if they're running,
   - installs what's needed (`pyirsdk`, `PySide6`),
   - takes the old overlays out of Windows startup and adds the HUD instead,
   - starts the HUD.
2. Look for the icon in the tray (bottom right of the taskbar). **Double-click it for Settings.**
3. Want to see it without iRacing? **`Demo.bat`** runs both overlays with simulated data.

From then on it starts with Windows, waits in the tray, and shows the overlays only while you're in
the car on track (not in the garage, menus or replays).

iRacing has to run in **windowed or borderless (fullscreen windowed)** mode. Exclusive fullscreen
draws over every overlay.

## Hotkeys (work while driving)
| Keys | What it does |
|---|---|
| Ctrl+Shift+D | hide / show the dash |
| Ctrl+Shift+S | hide / show the side indicator |
| Ctrl+Shift+T | side indicator test sweep (10 s of simulated traffic) |
| Ctrl+Shift+P | hide / show the pit-lane relative |
| Ctrl+Shift+B | hide / show the team pit board |
| Ctrl+Shift+E | layout mode: move and resize the overlays |

A hotkey hide lasts until you press it again or close iRacing. Change any hotkey in Settings.

## Moving things
- **Dash:** drag it to move, mouse wheel to resize. Right-click it for more.
  Clicking it never takes focus away from iRacing.
- **Layout mode** (tray menu, Settings, or Ctrl+Shift+E) shows the dash with an outline and plays
  simulated traffic on the side triangles, so you can place everything outside a session.
  Double-click the dash or press the hotkey again when you're done.
- **Side indicator:** a triangle on each screen edge, pointing in, shows when a car is alongside.
  It slides up when their car is further ahead and down when it's further behind; the middle (small
  tick) is door to door. The triangle is one bold colour; its position shows the overlap.
  (iRacing doesn't give the side-to-side gap between cars, so that can't be shown.) Colour-by-overlap
  and grow-when-close are optional. Change size, slide distance, colours etc. in
  Settings → Side indicator.
  It stays on the monitor you pick in Settings even if Windows starts on another screen: it's
  placed again every time you go on track and whenever a screen is switched on, off or changed,
  and the chosen monitor is remembered by its identity, not its number in the list.
  **Dash lights style:** set *Indicator style* to *Dash lights* for a race-car style warning-light module
  on each edge instead. The lamps simply light amber while a car is alongside on that side, with no
  position shown. Choose round LEDs or rectangular bars, the number of lamps, size, colour and height,
  whether they flash, and whether the unlit housing stays on screen like a real dash.

## Pit-lane relative (only when you need it)
There's no relative on screen during green-flag racing. A pit board appears only when:
- your **pit limiter** is on, or
- you're **off track** (all four wheels off, the same as iRacing's 1x) for more than 1 s. Two wheels
  over the line doesn't count, and a quick corner cut is ignored; change the time in Settings, or
- you've **lost control**: the car is sliding more than 35° sideways for a quarter of a second, or
  rolling backwards. This shows straight away in a spin, even if you never leave the track, or
- you're **stopped on track** (after a spin, say) for about 0.7 s. Not while waiting on the grid.

It stays up for 4 s after, so you can see the gaps while you rejoin or leave the pit lane.
Cars ahead are listed above you, cars behind below. The gap is in seconds at racing pace, so a car
2.5 s behind arrives in about 2.5 s. Gaps to cars behind turn **amber** within 4 s and **red**
within 2 s. Names are red-ish for a car a lap up on you and blue for a car a lap down; PIT / OFF
mark cars in the pit lane or off track.

Move it in layout mode (drag it, scroll to resize). *Settings → Pit-lane relative* has the triggers, the
stopped speed, how long it lingers, how many cars, colours and size. There's also an optional
"quick look" hotkey (not set by default) that shows it for a few seconds on demand, and a
*Preview* button to see it outside a session.

## Team pit board (updates once a lap)
Stays on screen and changes once a lap, about 1 s after you cross the line, with what a GT3 or
LMP team would hang over the pit wall:
- **Position** in your class.
- **Gap to the car ahead** in position (+), measured at the line this lap.
- **Gap to the car behind** in position (−), measured when they crossed the line after you on the
  last lap (they haven't got there yet this lap), the same way a real team times it.
- **Gained / lost** since the last board: green ▲ you gained, red ▼ you lost.
- **TRACK:** the cars nearest you on track right now, any class, including lapped traffic
  (blue = a lap down, red = a lap up on you).
- **Lap**, **laps or time to go**, and your **last lap**.

In practice and qualifying the gaps are to the best laps of the cars either side of you in the times.
A "~" in front of a gap means it's an estimate (no line timing for that car yet, e.g. the first lap).
For the full real-team feel, set *Show* to *Only after the line* in Settings → Team pit board: then
it appears for 12 s after each line crossing and disappears, like passing the pit wall.

## Settings
Everything is in the Settings window and applies straight away. It's saved to
`%APPDATA%\SimRacingHUD\config.json` (the **Open settings folder** button in Settings goes there),
so updates never touch it. Delete that file to go back to the defaults.

## Files
| File | What it's for |
|---|---|
| `setup.bat` | one-time setup (safe to run again) |
| `Start HUD.bat` | start it by hand; if it's already running, opens Settings |
| `Demo.bat` | simulated data, no iRacing needed |
| `HUD Troubleshoot.bat` | restart with a console that shows errors |
| `Remove from startup.bat` | stop it starting with Windows |
| `%APPDATA%\SimRacingHUD\hud.log` | errors from the background copy |
| `overlays/dash/dashes/` | one dash page per car (named after iRacing's car path) plus `default.html` |

The dash pages still work in a browser: `http://127.0.0.1:8765/dash` (add `?demo` to preview).
For a dash screen on another device, tick **Network → Let other devices open the dash** and restart.

## If something goes wrong
- One overlay hitting an error doesn't stop the others. You'll get a tray message and the details go
  to `hud.log`.
- **"Hotkey not set":** another program already uses that key combination. Pick another one in Settings.
- **"Port 8765 is already in use":** the old dash is probably still running. Run `setup.bat` again,
  or restart the PC.

## Adding an overlay later
1. Make a folder in `overlays/` with a class based on `overlays/base.py` → `Overlay`.
2. Give it an `id`, a `title`, `DEFAULTS` (its settings) and `VARS` (the iRacing variables it reads).
3. Add it to `OVERLAYS` in `overlays/__init__.py`.

Its Settings tab, hotkeys and tray entries come from its `settings_spec()`, `hotkeys()` and
`build_tray()`. Telemetry arrives each frame in `tick(frame, ctx)`: `frame.vars` has the variables it
asked for, `frame.session` has the car, track length and shift-light RPMs.

```
sim-racing-hud/
  hud.py              start here
  core/               telemetry reader, hotkeys, web server, settings file, Windows helpers
  overlays/           dash/, side_indicator/, pit_board/, team_board/
  ui/settings.py      the settings window
  packaging/          installer build (PyInstaller + Inno Setup)
  .github/workflows/  builds and publishes a release
```

## Publishing a new version (for the owner)
1. Get the changes into this repository.
2. On GitHub: **Actions → Release → Run workflow**. Type the new version (e.g. `1.1.0`, always higher
   than the last) and a line or two of what's new.
3. About 10 minutes later the release appears under Releases, and everyone's HUD offers the update.
