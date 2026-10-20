"""
Sim Racing HUD: all the iRacing overlays in one app.

    python hud.py                    run (waits in the tray; overlays show while you drive)
    python hud.py --demo             simulated data, no iRacing needed
    python hud.py --install-startup  start with Windows (and take the old separate overlays out of startup)
    python hud.py --remove-startup   stop starting with Windows

Requires: pip install pyirsdk PySide6   (setup.bat does this)
iRacing must run in windowed or borderless mode; exclusive fullscreen covers every overlay.
"""
import argparse
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import paths  # noqa: E402

LOG_PATH = paths.LOG_PATH


def setup_log():
    """With pythonw there's no console, so errors go to hud.log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        paths.ensure_data_dir()
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    except Exception:
        class Null:
            def write(self, *_): pass
            def flush(self): pass
        sys.stdout = sys.stderr = Null()


def main():
    from core.version import VERSION
    ap = argparse.ArgumentParser(description=f"Sim Racing HUD {VERSION}")
    ap.add_argument("--demo", action="store_true", help="simulated data, no iRacing needed")
    ap.add_argument("--install-startup", action="store_true")
    ap.add_argument("--remove-startup", action="store_true")
    args = ap.parse_args()

    from core import winutil
    if args.install_startup:
        for name in winutil.remove_old_entries():
            print(f"Took the old '{name}' out of Windows startup.")
        if winutil.install_startup():
            print("The HUD now starts with Windows. It waits in the tray and only shows while you drive.")
        return 0
    if args.remove_startup:
        print("Removed from Windows startup." if winutil.remove_startup() else "It wasn't set to start with Windows.")
        return 0

    setup_log()
    import time
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting version {VERSION}")
    sys.excepthook = lambda *e: traceback.print_exception(*e)
    from core.app import run
    return run(demo=args.demo)


if __name__ == "__main__":
    sys.exit(main())
