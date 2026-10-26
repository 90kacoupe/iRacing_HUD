"""Side indicator: a triangle on each screen edge that shows when a car is alongside.

Position is shown only by where the triangle sits as it slides up and down the edge:
    high on the screen = their car is ahead (alongside your nose)
    middle             = door to door
    low on the screen  = their car is behind (alongside your rear)

Alternative style ("lights"): a dash warning-light module on each edge, lamps that simply
light up while a car is alongside, like the blind-spot lights on a real race car.

The triangle is one bold colour (red by default). iRacing gives no side-to-side position
for other cars, so the gap between cars can't be shown. Optional settings can colour it by
overlap or grow it when door to door.
"""
import math
import time

from PySide6.QtCore import Qt, QPointF, QRect, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QPainter, QPolygonF, QAction, QRadialGradient, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from core import winutil
from core.demo import DemoTraffic
from overlays import base
from .tracker import SideTracker, UNKNOWN, side_data_from_vars


def _rgb(hex_text, fallback=(255, 176, 0)):
    try:
        c = QColor(hex_text)
        return (c.red(), c.green(), c.blue()) if c.isValid() else fallback
    except Exception:
        return fallback


def _mix(a, b, k):
    return tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(3))


def closeness(delta_m, car_len):
    """0 = just overlapping (nose to tail), 1 = exactly door to door."""
    return max(0.0, min(1.0, 1.0 - abs(delta_m) / max(car_len, 0.1)))


def color_for(k, far, mid, near):
    """Three-stop gradient: far (k=0) -> mid (k=0.5) -> near (k=1)."""
    if k < 0.5:
        return _mix(far, mid, k / 0.5)
    return _mix(mid, near, (k - 0.5) / 0.5)


class SideMarker(QWidget):
    PAD = 3  # px around the triangle so the outline isn't clipped

    def __init__(self, side, overlay):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.side = side
        self.ov = overlay
        self.setWindowTitle("Sim Racing HUD - side indicator")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.targets = []   # deltas (m) or UNKNOWN
        self.shown = []     # smoothed deltas being drawn
        self.alpha = 0.0
        self._painted = False
        self._house_on = False   # unlit dash-light housing currently drawn

    def _max_scale(self):
        return 1.0 + float(self.ov.cfg["grow_when_close"])

    def _lights_box(self):
        """(housing width, housing height, glow margin) for the dash-light style."""
        c = self.ov.cfg
        n = max(1, int(c["lights_count"]))
        size = float(c["lights_size"])
        gap = float(c["lights_gap"])
        bez = max(3.0, size * 0.28)
        lw = size * (1.6 if c["lights_shape"] == "bar" else 1.0)
        return lw + 2 * bez, n * size + (n - 1) * gap + 2 * bez, size * 0.6

    def place(self, screen):
        """Put this marker on its edge of `screen`. Returns the rect used."""
        rect = self._rect_for(screen.geometry())
        # Tell Qt which screen first, so the position is converted with that screen's
        # scaling (a window created on a smaller / differently scaled screen otherwise
        # lands in the wrong spot until it's placed a second time).
        wh = self.windowHandle()
        if wh is not None and wh.screen() is not screen:
            wh.setScreen(screen)
        self.setGeometry(rect)
        self.update()
        return rect

    def _rect_for(self, geo):
        c = self.ov.cfg
        if c["style"] == "lights":
            hw, hh, glow = self._lights_box()
            w, h = int(math.ceil(hw + 2 * glow)), int(math.ceil(hh + 2 * glow))
            cy = geo.top() + int(geo.height() * c["lights_center_frac"])
            if self.side == "L":
                x = geo.left() + int(c["edge_margin"]) - int(glow)
            else:
                x = geo.right() + 1 - int(c["edge_margin"]) - w + int(glow)
            return QRect(x, cy - h // 2, w, h)
        w = int(math.ceil(float(c["triangle_depth"]) * self._max_scale())) + 2 * self.PAD
        h = int(geo.height() * c["bar_height_frac"])
        h = max(h, int(float(c["triangle_height"]) * self._max_scale()) + 2 * self.PAD)
        cy = geo.top() + int(geo.height() * c["bar_center_frac"])
        if self.side == "L":
            x = geo.left() + int(c["edge_margin"])
        else:
            x = geo.right() + 1 - int(c["edge_margin"]) - w
        return QRect(x, cy - h // 2, w, h)

    def harden(self):
        winutil.add_ex_style(self, winutil.WS_EX_LAYERED | winutil.WS_EX_TRANSPARENT
                             | winutil.WS_EX_NOACTIVATE | winutil.WS_EX_TOOLWINDOW | winutil.WS_EX_TOPMOST)

    def step(self, dt, targets):
        c = self.ov.cfg
        self.targets = list(targets)
        if self.targets:
            if len(self.shown) != len(self.targets) or self.alpha < 0.05:
                self.shown = list(self.targets)
            else:
                s = c["smoothing_s"]
                k = 1.0 if s <= 0 else 1.0 - math.exp(-dt / s)
                self.shown = [tgt if (cur is UNKNOWN or tgt is UNKNOWN) else cur + (tgt - cur) * k
                              for cur, tgt in zip(self.shown, self.targets)]
            self.alpha = min(1.0, self.alpha + dt / max(c["fade_in_s"], 1e-3))
        else:
            self.alpha = max(0.0, self.alpha - dt / max(c["fade_out_s"], 1e-3))
        # The window stays shown and paints nothing when clear, so it never has to be
        # re-shown (which could take focus).
        house = self._housing_wanted()
        if self.alpha > 0 or self._painted or house != self._house_on:
            self._painted = self.alpha > 0
            self._house_on = house
            self.update()

    def _housing_wanted(self):
        """The unlit housing shows only while you're on track (or testing / in layout mode)."""
        c = self.ov.cfg
        return (c["style"] == "lights" and bool(c["lights_show_when_clear"])
                and bool(getattr(self.ov, "on_track", False)))

    # ---- dash-light style ----------------------------------------------------------
    def _paint_lights(self, p):
        c = self.ov.cfg
        col = self.ov.colors
        a = self.alpha
        if c["lights_flash"] and a > 0:
            hz = max(0.5, float(c["lights_flash_hz"]))
            if (time.monotonic() * hz) % 1.0 >= 0.5:
                a = 0.0                                  # off half of each flash
        show_housing = self._housing_wanted()
        if a <= 0 and not show_housing and self.alpha <= 0:
            return
        hw, hh, glow = self._lights_box()
        # Housing fades with the light unless it's set to stay on screen.
        house_a = 1.0 if show_housing else self.alpha
        n = max(1, int(c["lights_count"]))
        size = float(c["lights_size"])
        gap = float(c["lights_gap"])
        bez = (hw - size * (1.6 if c["lights_shape"] == "bar" else 1.0)) / 2.0
        lw = hw - 2 * bez
        x0, y0 = glow, glow
        rgb = col["light"]

        p.setPen(QPen(QColor(70, 70, 70, int(255 * house_a)), 1.5))
        p.setBrush(QColor(12, 12, 12, int(235 * house_a)))
        p.drawRoundedRect(QRectF(x0, y0, hw, hh), bez * 1.2, bez * 1.2)

        for i in range(n):
            r = QRectF(x0 + bez, y0 + bez + i * (size + gap), lw, size)
            ctr = r.center()
            rad = (size if c["lights_shape"] == "round" else max(lw, size)) / 2.0
            # Bloom around a lit lens, spilling over the housing like a real LED.
            if a > 0:
                g = QRadialGradient(ctr, rad * 2.0)
                g.setColorAt(0.0, QColor(rgb[0], rgb[1], rgb[2], int(150 * a)))
                g.setColorAt(1.0, QColor(rgb[0], rgb[1], rgb[2], 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(ctr, rad * 2.0, rad * 2.0)
            # Lens: dim tinted glass when off, hot centre when on.
            g = QRadialGradient(ctr, rad)
            off = [int(v * 0.22) for v in rgb]
            if a > 0:
                hot = [min(255, int(v + (255 - v) * 0.75)) for v in rgb]
                g.setColorAt(0.0, QColor(*_mix(off, hot, a), int(255 * max(a, house_a))))
                g.setColorAt(0.55, QColor(*_mix(off, rgb, a), int(255 * max(a, house_a))))
                g.setColorAt(1.0, QColor(*_mix(off, [int(v * 0.7) for v in rgb], a), int(255 * max(a, house_a))))
            else:
                g.setColorAt(0.0, QColor(*[int(v * 0.32) for v in rgb], int(255 * house_a)))
                g.setColorAt(1.0, QColor(*off, int(255 * house_a)))
            p.setBrush(g)
            p.setPen(QPen(QColor(0, 0, 0, int(200 * max(a, house_a))), 1.2))
            if c["lights_shape"] == "round":
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, size * 0.18, size * 0.18)

    def _triangle(self, cy, scale):
        """Base on the screen edge, tip pointing in toward the middle of the screen."""
        c = self.ov.cfg
        th = float(c["triangle_height"]) * scale
        td = float(c["triangle_depth"]) * scale
        if self.side == "L":
            x0, x1 = self.PAD, self.PAD + td
        else:
            x0, x1 = self.width() - self.PAD, self.width() - self.PAD - td
        return QPolygonF([QPointF(x0, cy - th / 2), QPointF(x1, cy), QPointF(x0, cy + th / 2)])

    def paintEvent(self, _):
        c = self.ov.cfg
        if c["style"] == "lights":
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            self._paint_lights(p)
            p.end()
            return
        col = self.ov.colors
        a = self.alpha
        if a <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        car_len = float(c["car_length_m"])
        grow = float(c["grow_when_close"])
        base_h = float(c["triangle_height"])
        # Room for the triangle's centre to travel without its corners leaving the window.
        half = base_h * (1.0 + grow) / 2.0 + self.PAD
        top, bottom = half, self.height() - half
        mid = self.height() / 2.0
        span = 2.0 * float(c["range_car_lengths"]) * car_len    # metres covered top to bottom
        px_per_m = max(bottom - top, 1.0) / max(span, 0.1)

        edge_x = self.PAD if self.side == "L" else self.width() - self.PAD
        if c["show_guide"]:
            p.setPen(QPen(QColor(255, 255, 255, int(255 * c["guide_opacity"] * a)), 2.0))
            p.drawLine(QPointF(edge_x, top), QPointF(edge_x, bottom))

        # Farthest first so the closest car is drawn on top.
        items = sorted(self.shown, key=lambda d: -1.0 if d is UNKNOWN else -abs(d))
        for d in items:
            if d is UNKNOWN:
                rgb, cy, scale, op = col["unknown"], mid, 1.0, c["triangle_opacity"] * 0.6
            else:
                k = closeness(d, car_len)
                if c["color_by_overlap"]:
                    rgb = color_for(k, col["far"], col["mid"], col["near"])
                else:
                    rgb = col["single"]
                cy = max(top, min(bottom, mid - d * px_per_m))   # ahead = up
                scale = 1.0 + grow * k
                op = c["triangle_opacity"]
            p.setBrush(QColor(rgb[0], rgb[1], rgb[2], int(255 * op * a)))
            p.setPen(QPen(QColor(0, 0, 0, int(170 * a)), 1.5))   # dark edge for bright skies
            p.drawPolygon(self._triangle(cy, scale))

        # Door-to-door mark, drawn on top so the triangle can be lined up against it.
        if c["show_center_mark"]:
            w = float(c["triangle_depth"]) * (1.0 + grow) * float(c["center_mark_length"])
            x2 = edge_x + w if self.side == "L" else edge_x - w
            t = float(c["center_mark_thickness"])
            op = float(c["center_mark_opacity"]) * a
            mrgb = col["mark"]
            p.setPen(QPen(QColor(0, 0, 0, int(220 * op)), t + 3.0, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(QPointF(edge_x, mid), QPointF(x2, mid))
            p.setPen(QPen(QColor(mrgb[0], mrgb[1], mrgb[2], int(255 * op)), t, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(QPointF(edge_x, mid), QPointF(x2 - (1.5 if self.side == "L" else -1.5), mid))
        p.end()


class SideIndicatorOverlay(base.Overlay):
    id = "side_indicator"
    title = "Side indicator"
    DEFAULTS = {
        "enabled": True,
        "hotkey": "ctrl+shift+s",
        "test_hotkey": "ctrl+shift+t",
        "monitor": 0,
        "monitor_id": "",        # the chosen monitor's identity, so it's found even if Windows reorders screens
        "style": "triangle",
        "lights_count": 3,
        "lights_shape": "round",
        "lights_size": 22,
        "lights_gap": 6,
        "lights_center_frac": 0.50,
        "color_light": "#ffa000",
        "lights_flash": False,
        "lights_flash_hz": 4.0,
        "lights_show_when_clear": False,
        "triangle_height": 56,
        "triangle_depth": 40,
        "grow_when_close": 0.0,
        "bar_height_frac": 0.40,
        "bar_center_frac": 0.50,
        "edge_margin": 6,
        "car_length_m": 4.7,
        "range_car_lengths": 1.5,
        "show_guide": False,
        "show_center_mark": True,
        "center_mark_length": 1.0,
        "center_mark_thickness": 4,
        "center_mark_opacity": 0.95,
        "color_mark": "#ffffff",
        "color_by_overlap": False,
        "color_single": "#ff1e1e",
        "color_far": "#ffd400",
        "color_mid": "#ff7a00",
        "color_near": "#ff1e1e",
        "color_unknown": "#ffb000",
        "triangle_opacity": 0.95,
        "guide_opacity": 0.30,
        "fade_in_s": 0.06,
        "fade_out_s": 0.25,
        "smoothing_s": 0.05,
    }
    VARS = ("CarLeftRight", "PlayerCarIdx", "CarIdxLapDistPct", "CarIdxTrackSurface", "CarIdxOnPitRoad")

    def start(self):
        self.on_track = False
        self.paused = False          # hotkey hide; lasts until pressed again or iRacing closes
        self.test_until = 0.0
        self.test_demo = None
        self.layout_demo = None
        self.tracker = SideTracker(self.cfg["car_length_m"])
        self._read_colors()
        self.bars = [SideMarker("L", self), SideMarker("R", self)]
        self._last_placed = None
        self._was_on_track = False
        for b in self.bars:
            b.show()
            b.harden()
        self._place()
        # Re-place whenever the screens change: a monitor switched on / off, a new primary,
        # a resolution or scaling change, or a marker ending up on another screen. Windows
        # sends several of these in a burst, so they're gathered and handled once.
        self._replace_timer = QTimer(singleShot=True, interval=500)
        self._replace_timer.timeout.connect(self._replace_now)
        qt = QGuiApplication.instance()
        qt.screenAdded.connect(self._screen_added)
        qt.screenRemoved.connect(lambda *_: self._replace_soon())
        qt.primaryScreenChanged.connect(lambda *_: self._replace_soon())
        for scr in QGuiApplication.screens():
            self._watch_screen(scr)
        for b in self.bars:
            if b.windowHandle() is not None:
                b.windowHandle().screenChanged.connect(lambda *_: self._replace_soon())

    # ---- settings --------------------------------------------------------------
    def _read_colors(self):
        c = self.cfg
        self.colors = {"light": _rgb(c["color_light"], (255, 160, 0)), "single": _rgb(c["color_single"], (255, 30, 30)), "far": _rgb(c["color_far"]), "mid": _rgb(c["color_mid"]),
                       "near": _rgb(c["color_near"]), "unknown": _rgb(c["color_unknown"]),
                       "mark": _rgb(c["color_mark"], (255, 255, 255))}

    @staticmethod
    def screen_id(scr):
        """Something that identifies a physical monitor, not its place in the list."""
        try:
            parts = [scr.manufacturer(), scr.model(), scr.serialNumber()]
        except Exception:
            parts = []
        ident = "|".join(p or "" for p in parts)
        return ident if ident.strip("|") else "name:" + scr.name()

    def _target_screen(self):
        screens = QGuiApplication.screens()
        if not screens:
            return None
        want = self.cfg.get("monitor_id") or ""
        if want:
            for i, scr in enumerate(screens):
                if self.screen_id(scr) == want or "name:" + scr.name() == want:
                    if int(self.cfg["monitor"]) != i:
                        self.cfg["monitor"] = i          # keep the Settings list showing the right one
                        self.app.save_config_soon()
                    return scr
        i = int(self.cfg["monitor"])
        return screens[i] if 0 <= i < len(screens) else QGuiApplication.primaryScreen()

    def _place(self):
        scr = self._target_screen()
        if scr is None:
            return
        rects = [b.place(scr) for b in self.bars]
        for b in self.bars:
            b.harden()
        where = (scr.name(), tuple((r.x(), r.y(), r.width(), r.height()) for r in rects))
        if where != self._last_placed:
            self._last_placed = where
            g = scr.geometry()
            print(f"[side_indicator] placed on {scr.name()} "
                  f"({g.width()}x{g.height()} at {g.x()},{g.y()}, scale {scr.devicePixelRatio():g})")

    def _replace_soon(self):
        if getattr(self, "_replace_timer", None) is not None:
            self._replace_timer.start()

    def _replace_now(self):
        self.app.call(self, "_place")

    def _watch_screen(self, scr):
        scr.geometryChanged.connect(lambda *_: self._replace_soon())
        scr.logicalDotsPerInchChanged.connect(lambda *_: self._replace_soon())

    def _screen_added(self, scr):
        self._watch_screen(scr)
        self._replace_soon()

    def apply_settings(self, key=None):
        self._read_colors()
        self.tracker.set_car_length(self.cfg["car_length_m"])
        if key == "monitor":
            screens = QGuiApplication.screens()
            i = int(self.cfg["monitor"])
            if 0 <= i < len(screens):
                self.cfg["monitor_id"] = self.screen_id(screens[i])
        self._place()

    def settings_spec(self):
        screens = QApplication.screens()
        monitors = [(i, f"{i + 1}: {s.name()} ({s.geometry().width()}x{s.geometry().height()})")
                    for i, s in enumerate(screens)] or [(0, "1")]
        return [
            base.check("enabled", "Use the side indicator"),
            base.hotkey("hotkey", "Hide / show hotkey"),
            base.hotkey("test_hotkey", "Test sweep hotkey", "Plays 10 s of simulated traffic"),
            base.button("Play a test sweep now", self.test_sweep),
            base.choice("style", "Indicator style", [
                ("triangle", "Sliding triangle (shows where the car is)"),
                ("lights", "Dash lights (on when a car is alongside)")]),
            base.choice("monitor", "Monitor", monitors),
            base.number("edge_margin", "Gap from screen edge", 0, 400, suffix=" px"),
            base.note("Tip: turn on layout mode (button below) to see the indicator with simulated traffic while you change these."),
            base.header("Dash lights style"),
            base.choice("lights_shape", "Lamp shape", [("round", "Round LEDs"), ("bar", "Rectangular LED bars")]),
            base.number("lights_count", "Lamps per side", 1, 8),
            base.number("lights_size", "Lamp size", 6, 120, suffix=" px"),
            base.number("lights_gap", "Gap between lamps", 0, 60, suffix=" px"),
            base.percent("lights_center_frac", "Height on screen", 0, 100, "0 % = top of screen, 100 % = bottom"),
            base.color("color_light", "Lamp colour"),
            base.check("lights_flash", "Flash while a car is alongside"),
            base.decimal("lights_flash_hz", "Flash rate", 0.5, 10, 0.5, 1, " Hz"),
            base.check("lights_show_when_clear", "Keep the unlit housing on screen when clear",
                       "Like a real dash: the lamps are always there, they just light up"),
            base.header("Sliding triangle style"),
            base.number("triangle_height", "Triangle height", 10, 300, suffix=" px",
                        tip="Along the screen edge"),
            base.number("triangle_depth", "Triangle depth", 6, 300, suffix=" px",
                        tip="How far it points in from the edge"),
            base.percent("grow_when_close", "Grow when door to door", 0, 100,
                         "Extra size when fully alongside"),
            base.header("Where the triangle slides"),
            base.percent("bar_height_frac", "Slide distance", 5, 100,
                         "How much of the screen height the triangle travels over"),
            base.percent("bar_center_frac", "Door-to-door point", 0, 100,
                         "Where the triangle sits when side by side. 0 % = top of screen, 100 % = bottom"),
            base.decimal("range_car_lengths", "Range ahead / behind", 0.5, 5, 0.1, 1, " car lengths",
                         "Distance from door to door to the top / bottom of the slide"),
            base.decimal("car_length_m", "Car length", 2.5, 8, 0.1, 1, " m",
                         "iRacing doesn't publish it, so this is used for overlap"),
            base.header("Triangle colour"),
            base.color("color_single", "Triangle colour"),
            base.check("color_by_overlap", "Change colour with overlap instead",
                       "Uses the three colours below; the single colour above is ignored"),
            base.color("color_far", "  Just overlapping"),
            base.color("color_mid", "  Half alongside"),
            base.color("color_near", "  Door to door"),
            base.color("color_unknown", "Car the spotter sees but can't be placed"),
            base.percent("triangle_opacity", "Triangle opacity", 10, 100),
            base.header("Triangle reference marks"),
            base.check("show_center_mark", "Tick at the door-to-door point"),
            base.percent("center_mark_length", "Tick length", 10, 200, "100 % = as long as the triangle is deep"),
            base.number("center_mark_thickness", "Tick thickness", 1, 20, suffix=" px"),
            base.color("color_mark", "Tick colour"),
            base.percent("center_mark_opacity", "Tick opacity", 10, 100),
            base.check("show_guide", "Faint line along the slide path"),
            base.percent("guide_opacity", "Slide line opacity", 0, 100),
            base.header("Motion"),
            base.decimal("fade_in_s", "Fade in", 0, 1, 0.01, 2, " s"),
            base.decimal("fade_out_s", "Fade out", 0, 2, 0.05, 2, " s"),
            base.decimal("smoothing_s", "Movement smoothing", 0, 0.5, 0.01, 2, " s"),
        ]

    # ---- actions ---------------------------------------------------------------
    def toggle(self):
        self.paused = not self.paused
        self._sync_tray()

    def test_sweep(self):
        self.paused = False
        self._sync_tray()
        self.test_demo = DemoTraffic(car_length_m=self.cfg["car_length_m"])
        self.test_until = time.monotonic() + 10.0

    def hotkeys(self):
        return {"side.toggle": ("hotkey", self.toggle), "side.test": ("test_hotkey", self.test_sweep)}

    def build_tray(self, menu):
        self.act_toggle = QAction("Hide side indicator", menu, triggered=lambda *_: self.toggle())
        menu.addAction(self.act_toggle)
        menu.addAction(QAction("Side indicator test sweep (10 s)", menu, triggered=lambda *_: self.test_sweep()))

    def _sync_tray(self):
        if getattr(self, "act_toggle", None):
            self.act_toggle.setText("Show side indicator" if self.paused else "Hide side indicator")

    def on_session_end(self):
        if self.paused:
            self.paused = False
            self._sync_tray()

    def on_layout_mode(self, on):
        self.layout_demo = DemoTraffic(car_length_m=self.cfg["car_length_m"]) if on else None

    # ---- every frame -------------------------------------------------------------
    def tick(self, frame, ctx):
        data = None
        testing = ctx.now < self.test_until and self.test_demo is not None
        # On track = the app's shared "show overlays" state (driving, with the hide delay),
        # or a test sweep / layout mode. Nothing at all is drawn otherwise.
        self.on_track = bool(self.cfg["enabled"] and not self.paused
                             and (ctx.visible or ctx.layout_mode or testing))
        # Every time it's about to show (you go on track, test sweep, layout mode), place it
        # again on the chosen monitor. Catches any screen change since the app started.
        if self.on_track and not self._was_on_track:
            self._place()
        self._was_on_track = self.on_track
        if not self.cfg["enabled"]:
            pass
        elif ctx.layout_mode and self.layout_demo:
            data = self.layout_demo.read(ctx.now)
        elif ctx.now < self.test_until and self.test_demo:
            data = self.test_demo.read(ctx.now)
        elif not self.paused and frame.driving and ctx.visible:
            data = side_data_from_vars(frame.vars, frame.session.get("track_len_m", 0.0))

        if data is None:
            left, right = [], []
            self.tracker.sides.clear()
        else:
            left, right = self.tracker.update(*data)
        self.bars[0].step(ctx.dt, left)
        self.bars[1].step(ctx.dt, right)

    def keep_on_top(self):
        for b in self.bars:
            winutil.keep_topmost(b)

    def shutdown(self):
        if getattr(self, "_replace_timer", None) is not None:
            self._replace_timer.stop()
        for b in getattr(self, "bars", []):
            b.hide()
