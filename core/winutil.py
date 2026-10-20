"""Windows helpers: single instance, window styles, start with Windows."""
import os
import subprocess
import sys

IS_WINDOWS = os.name == "nt"

WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

# ---------------------------------------------------------------- one copy only
_held = []


def already_running(name):
    """True if another copy holds this name (Windows named mutex)."""
    if not IS_WINDOWS:
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    handle = k32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return True
    _held.append(handle)  # kept until this process exits
    return False


# ---------------------------------------------------------------- window styles
def add_ex_style(widget, flags):
    if not IS_WINDOWS:
        return
    import ctypes
    u = ctypes.windll.user32
    hwnd = int(widget.winId())
    u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | flags)  # GWL_EXSTYLE


def keep_topmost(widget):
    """Put the window back on top without taking focus (borderless games can cover it)."""
    if not IS_WINDOWS or not widget.isVisible():
        return
    import ctypes
    flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
    ctypes.windll.user32.SetWindowPos(int(widget.winId()), -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST


# ---------------------------------------------------------------- start with Windows
STARTUP_NAME = "Sim Racing HUD.lnk"
STARTUP_BAT = "Sim Racing HUD.bat"          # fallback if a shortcut can't be made
OLD_ENTRIES = ["LMP3 Dash Overlay.bat", "iRacing Side Indicator.lnk"]   # the two separate overlays


def startup_dir():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")


def startup_installed():
    d = startup_dir()
    return any(os.path.exists(os.path.join(d, n)) for n in (STARTUP_NAME, STARTUP_BAT))


def _pythonw():
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")   # runs without a console window
    return pyw if os.path.exists(pyw) else exe


def remove_old_entries():
    """Take the old separate dash / side indicator out of Windows startup. Returns what was removed."""
    removed = []
    for name in OLD_ENTRIES:
        p = os.path.join(startup_dir(), name)
        if os.path.exists(p):
            try:
                os.remove(p)
                removed.append(name)
            except Exception as e:
                print(f"Couldn't remove {name} from startup: {e}")
    return removed


def launch_command():
    """(program, arguments, working folder) that starts the HUD with no console window."""
    from . import paths
    if paths.FROZEN:
        return sys.executable, "", paths.APP_DIR
    script = os.path.join(paths.APP_DIR, "hud.py")
    return _pythonw(), f'"{script}"', paths.APP_DIR


def install_startup():
    if not IS_WINDOWS:
        return False
    d = startup_dir()
    if not os.path.isdir(d):
        print("Couldn't find the Windows Startup folder.")
        return False
    target, args, folder = launch_command()
    lnk = os.path.join(d, STARTUP_NAME)

    def q(s):
        return s.replace("'", "''")
    ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}');"
          f"$s.TargetPath = '{q(target)}';"
          f"$s.Arguments = '{q(args)}';"
          f"$s.WorkingDirectory = '{q(folder)}';"
          f"$s.Description = 'Sim Racing HUD overlays';"
          f"$s.Save()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       check=True, capture_output=True, creationflags=0x08000000)  # CREATE_NO_WINDOW
        ok = os.path.exists(lnk)
    except Exception:
        ok = False
    if not ok:  # fall back to a small batch file
        try:
            with open(os.path.join(d, STARTUP_BAT), "w") as f:
                f.write('@echo off\r\ncd /d "%s"\r\nstart "" "%s" %s\r\n' % (folder, target, args))
            ok = True
        except Exception as e:
            print("Couldn't add to Windows startup:", e)
    return ok


def remove_startup():
    removed = False
    for n in (STARTUP_NAME, STARTUP_BAT):
        p = os.path.join(startup_dir(), n)
        if os.path.exists(p):
            os.remove(p)
            removed = True
    return removed


def open_path(path):
    try:
        if IS_WINDOWS:
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print("Couldn't open", path, e)
