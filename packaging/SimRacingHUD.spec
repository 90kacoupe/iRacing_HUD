# PyInstaller build of the HUD: dist/SimRacingHUD/SimRacingHUD.exe plus its libraries.
# Run from the repo root:  pyinstaller packaging/SimRacingHUD.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (collect_submodules("overlays", filter=lambda m: True)   # loaded by name at run time
          + ["ui.settings", "irsdk", "yaml"])

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
