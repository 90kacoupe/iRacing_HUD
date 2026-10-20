"""Where things live.

APP_DIR   the program itself (the install folder, or this source folder).
DATA_DIR  your settings and log: %APPDATA%\\SimRacingHUD. Kept out of the program folder so
          updates never touch them and nobody's settings get shipped with the app.
"""
import os
import shutil
import sys

FROZEN = bool(getattr(sys, "frozen", False))      # running as the installed SimRacingHUD.exe

if FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "SimRacingHUD")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "hud.log")


def ensure_data_dir():
    """Make the settings folder, and bring over settings from before they moved here."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        print("Couldn't create the settings folder:", e)
        return
    old = os.path.join(APP_DIR, "config.json")
    if not os.path.exists(CONFIG_PATH) and os.path.exists(old):
        try:
            shutil.copyfile(old, CONFIG_PATH)
            print(f"Moved settings from {old} to {CONFIG_PATH}")
        except Exception as e:
            print("Couldn't copy the old config.json:", e)
