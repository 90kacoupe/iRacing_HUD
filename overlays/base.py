"""What every overlay looks like to the app.

To add an overlay:
  1. Make a folder in overlays/ with a class based on Overlay.
  2. Give it an id, a title, DEFAULTS (its settings) and VARS (iRacing variables it reads).
  3. Add it to OVERLAYS in overlays/__init__.py.
Its settings tab, hotkeys and tray entries appear automatically from
settings_spec(), hotkeys() and build_tray().
"""


class Context:
    """Passed to every overlay each frame."""
    __slots__ = ("now", "dt", "visible", "layout_mode", "demo")

    def __init__(self, now, dt, visible, layout_mode, demo):
        self.now = now                  # time.monotonic()
        self.dt = dt                    # seconds since the last frame
        self.visible = visible          # overlays should show (driving, with the hide delay applied)
        self.layout_mode = layout_mode  # the user is moving / resizing overlays
        self.demo = demo                # running with simulated data


class Overlay:
    id = ""
    title = ""
    DEFAULTS = {}
    VARS = ()

    def __init__(self, app):
        self.app = app
        self.failed = False

    @property
    def cfg(self):
        return self.app.config[self.id]

    def start(self): ...                       # make windows
    def tick(self, frame, ctx): ...            # ~60 times a second
    def settings_spec(self): return []         # rows for its settings tab (see helpers below)
    def apply_settings(self, key=None): ...    # a setting changed (key None = several / general)
    def hotkeys(self): return {}               # {action name: (config key, function)}
    def build_tray(self, menu): ...            # add entries to the tray menu
    def keep_on_top(self): ...                 # every 2 s
    def on_session_end(self): ...              # iRacing closed / left the session
    def on_layout_mode(self, on): ...
    def shutdown(self): ...


# ---- settings rows ------------------------------------------------------------------
def header(text):
    return {"type": "header", "label": text}


def note(text):
    return {"type": "note", "label": text}


def check(key, label, tip=""):
    return {"type": "bool", "key": key, "label": label, "tip": tip}


def number(key, label, lo, hi, step=1, suffix="", tip=""):
    return {"type": "int", "key": key, "label": label, "lo": lo, "hi": hi, "step": step,
            "suffix": suffix, "tip": tip}


def decimal(key, label, lo, hi, step=0.1, decimals=1, suffix="", tip=""):
    return {"type": "float", "key": key, "label": label, "lo": lo, "hi": hi, "step": step,
            "decimals": decimals, "suffix": suffix, "tip": tip}


def percent(key, label, lo=0, hi=100, tip=""):
    """Stored as 0..1, shown as 0..100 %."""
    return {"type": "pct", "key": key, "label": label, "lo": lo, "hi": hi, "tip": tip}


def color(key, label, tip=""):
    return {"type": "color", "key": key, "label": label, "tip": tip}


def hotkey(key, label, tip=""):
    return {"type": "hotkey", "key": key, "label": label, "tip": tip}


def choice(key, label, options, tip=""):
    """options: [(value, text), ...]"""
    return {"type": "choice", "key": key, "label": label, "options": options, "tip": tip}


def button(label, fn, tip=""):
    return {"type": "button", "label": label, "fn": fn, "tip": tip}


def toggle(label, get, set, tip=""):
    """A checkbox backed by functions instead of a config value."""
    return {"type": "toggle", "label": label, "get": get, "set": set, "tip": tip}
