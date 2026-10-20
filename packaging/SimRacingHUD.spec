# PyInstaller build of the HUD: dist/SimRacingHUD/SimRacingHUD.exe plus its libraries.
# Run from the repo root:  pyinstaller packaging/SimRacingHUD.spec --noconfirm
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
# collect_submodules can only find the app's own packages if the repo root is on the path.
# Without this it silently returns nothing and only the overlays reached by a normal
# import get bundled (v1.0.0 shipped with just the pit-lane relative because of this).
sys.path.insert(0, ROOT)

from overlays import OVERLAYS                                     # noqa: E402

hidden = (collect_submodules("overlays", filter=lambda m: True)   # loaded by name at run time
          + [module for module, _ in OVERLAYS]
          + ["ui.settings", "irsdk", "yaml"])
_missing = [m for m, _ in OVERLAYS if m not in collect_submodules("overlays", filter=lambda m: True)]
if _missing:
    raise SystemExit(f"Build stopped: these overlays couldn't be found to bundle: {_missing}")

a = Analysis(
    [os.path.join(ROOT, "hud.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "overlays", "dash", "dashes"), os.path.join("overlays", "dash", "dashes"))],
    hiddenimports=hidden,
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SimRacingHUD",
    console=False,                       # no console window; errors go to hud.log
    icon=os.path.join(SPECPATH, "hud.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SimRacingHUD", upx=False)
