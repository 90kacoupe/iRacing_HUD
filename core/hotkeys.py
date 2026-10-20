"""Global hotkeys that work while iRacing has focus (Windows RegisterHotKey).

Hotkeys are written like "ctrl+shift+d". Modifiers: ctrl, shift, alt, win.
Key: a letter, a digit, F1-F24, numpad0-numpad9, or space, insert, delete,
home, end, pageup, pagedown.
"""
import os
import threading

_VK_NAMES = {"space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
             "insert": 0x2D, "delete": 0x2E}
_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8, "meta": 0x8}

WM_HOTKEY = 0x0312
WM_REBIND = 0x8001  # WM_APP + 1


def parse_hotkey(text):
    """'ctrl+shift+d' -> (modifier flags, virtual key code), or None if it can't be read."""
    mods, vk = 0, None
    for part in [p.strip().lower() for p in str(text).split("+") if p.strip()]:
        if part in _MODS:
            mods |= _MODS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("numpad") and part[6:].isdigit():
            vk = 0x60 + int(part[6:])
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x6F + int(part[1:])
        elif part in _VK_NAMES:
            vk = _VK_NAMES[part]
        else:
            return None
    return (mods | 0x4000, vk) if vk else None   # 0x4000 = don't repeat while held


# Qt key-sequence text <-> our text
_FROM_QT = {"pgup": "pageup", "pgdown": "pagedown", "ins": "insert", "del": "delete", "meta": "win"}
_TO_QT = {"pageup": "PgUp", "pagedown": "PgDown", "insert": "Ins", "delete": "Del", "win": "Meta"}


def from_qt(text):
    text = (text or "").split(",")[0].strip()
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if text.endswith("++"):          # Qt writes the plus key as "+"; not supported here
        return ""
    if "num" in parts:                # keypad: Qt writes "Num+5"
        parts.remove("num")
        parts = [("numpad" + p) if p.isdigit() else p for p in parts]
    return "+".join(_FROM_QT.get(p, p) for p in parts)


def to_qt(text):
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    parts = [("num+" + p[6:]) if p.startswith("numpad") else p for p in parts]
    return "+".join(_TO_QT.get(p, p.capitalize() if len(p) > 1 else p.upper()) for p in parts)


def pretty(text):
    return to_qt(text).replace("Meta", "Win") if text else "(none)"


class GlobalHotkeys:
    """Runs a small Windows message loop on its own thread.

    on_press(name) is called from that thread; on_error(list of (name, text, why)) too.
    """

    def __init__(self, on_press, on_error):
        self.on_press = on_press
        self.on_error = on_error
        self.ok = os.name == "nt"
        self._pending = {}
        self._lock = threading.Lock()
        self._tid = None
        self._ready = threading.Event()
        if self.ok:
            threading.Thread(target=self._run, daemon=True, name="hotkeys").start()
            self._ready.wait(2)

    def set(self, bindings):
        """bindings: {name: "ctrl+shift+d"}. Replaces every hotkey."""
        with self._lock:
            self._pending = dict(bindings)
        if self.ok and self._tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_REBIND, 0, 0)

    def _run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # makes this thread's message queue
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._ready.set()
        ids = {}

        def rebind():
            for i in list(ids):
                user32.UnregisterHotKey(None, i)
            ids.clear()
            with self._lock:
                wanted = dict(self._pending)
            failed, used, n = [], {}, 1
            for name, text in wanted.items():
                if not text:
                    continue
                parsed = parse_hotkey(text)
                if not parsed:
                    failed.append((name, text, "isn't a key combination this app understands"))
                    continue
                if parsed in used:
                    failed.append((name, text, "is already used for another action here"))
                    continue
                if user32.RegisterHotKey(None, n, parsed[0], parsed[1]):
                    ids[n] = name
                    used[parsed] = name
                else:
                    failed.append((name, text, "is already used by another program"))
                n += 1
            if failed:
                try:
                    self.on_error(failed)
                except Exception:
                    pass

        rebind()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_REBIND:
                rebind()
            elif msg.message == WM_HOTKEY:
                name = ids.get(int(msg.wParam))
                if name:
                    try:
                        self.on_press(name)
                    except Exception:
                        pass
