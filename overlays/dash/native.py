"""The dash drawn natively with Qt, for the overlay window.

The overlay used to show the HTML dash pages in a built-in Chromium (QtWebEngine), which
runs its own processes, uses the graphics card and fetched /data 30 times a second.
This draws the same dash directly instead:

  * the boxes and labels are drawn once into a cached picture (again only after a resize
    or a page change),
  * the values are recomputed each frame but the window only repaints when something
    that's on screen changes (a digit, a shift light, the pit page).

The HTML pages in dashes/ are unchanged and still serve browsers and dash screens.

Each car's dash is a Layout: fixed positions in an 800-wide canvas, copied from its HTML
page. LAYOUTS maps iRacing car paths to them; DEFAULT_LAYOUT covers every other car.
"""
import math

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QWidget

FONT_FAMILIES = ["Bahnschrift", "DIN Alternate", "Arial Narrow", "Arial"]

# What the HTML page shows before the first data arrives.
WAITING_VALUES = (("best", "-:--.--"), ("fuel_lap", "0.00"), ("fuel_used", "0.00"), ("gear", "N"),
                  ("last", "-:--.--"), ("oil", "0.0"), ("pps", "-"), ("rain", "OFF"), ("rpm", "0"),
                  ("speed", "0"), ("tc", "-"), ("tfl", "--.-"), ("tfr", "--.-"), ("trl", "--.-"),
                  ("trr", "--.-"), ("water", "0"))


# ---- formatting (same results as the HTML page) -------------------------------------
def _num(v):
    if v is None or v == "":
        return math.nan
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def _round(x):
    """JavaScript Math.round (halves go up)."""
    return int(math.floor(x + 0.5))


def fixed(v, d):
    n = _num(v)
    return f"{n:.{d}f}" if math.isfinite(n) else "-"


def lap_time(v):
    s = _num(v)
    if not math.isfinite(s) or s <= 0:
        return "-:--.--"
    m = int(s // 60)
    r = s - m * 60
    txt = f"{r:.2f}"
    if txt.startswith("60"):          # 59.996 rounds up
        m, txt = m + 1, "0.00"
    return f"{m}:{'0' if float(txt) < 10 else ''}{txt}"


def map_value(v):
    n = _num(v)
    return str(_round(n)) if math.isfinite(n) else "-"


class FuelTracker:
    """Fuel used this lap and on the last full lap (same rules as the HTML page)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.lap, self.start, self.last_lap = None, None, 0.0
        self.used = 0.0

    def update(self, fuel, laps):
        if not math.isfinite(fuel):
            return
        if self.start is None or fuel > self.start + 0.5:       # first reading or a refuel
            self.start, self.lap = fuel, laps
        if math.isfinite(laps) and laps != self.lap:
            if self.lap is not None and math.isfinite(self.lap) and laps == self.lap + 1:
                self.last_lap = self.start - fuel
            self.start, self.lap = fuel, laps
        self.used = max(0.0, self.start - fuel)


class DemoDash:
    """Made-up values for demo mode and layout mode (the HTML page's ?demo)."""
    STEP = 1 / 30

    def __init__(self, now):
        self.t0 = self.t = now
        self.rpm, self.gear, self.fuel = 4200.0, 2, 40.0

    def read(self, now):
        while self.t + self.STEP <= now:
            self.t += self.STEP
            self.rpm += 70
            if self.rpm > 7350:
                self.rpm = 5200.0
                self.gear = self.gear + 1 if self.gear < 6 else 2
            self.fuel -= 0.0006
        el = now - self.t0
        return {
            "connected": True, "Rpms": self.rpm, "MaxRpm": 7500, "Gear": str(self.gear),
            "Speed": self.rpm / 45 + self.gear * 14, "LastLapTime": 102.381, "BestLapTime": 101.952,
            "Fuel": self.fuel, "CompletedLaps": 3 + int(el // 20), "OilPressure": 16.5,
            "WaterTemperature": 166, "TyrePressureFrontLeft": 26.9, "TyrePressureFrontRight": 26.9,
            "TyrePressureRearLeft": 26.9, "TyrePressureRearRight": 26.9,
            "LapDeltaToSessionBestLap": math.sin(el / 4) * 0.6, "PitLimiter": int(el // 12) % 2 == 1,
            "BrakeBias": 59.0, "ThrottlePct": 0.4, "dcTractionControl": 3, "dcThrottleShape": 4,
            "dcRainLight": 0, "DriverCarSLFirstRPM": 5600, "DriverCarSLLastRPM": 7000,
            "DriverCarSLBlinkRPM": 7200,
        }


# ---- layout ---------------------------------------------------------------------------
class Box:
    """A filled and/or outlined rectangle. Coordinates in canvas pixels, like CSS border-box."""

    def __init__(self, x, y, w, h, fill=None, border=None, width=0, radius=0):
        self.rect = QRectF(x, y, w, h)
        self.fill, self.border, self.width, self.radius = fill, border, width, radius

    def draw(self, p):
        r = self.rect
        if self.fill:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self.fill))
            p.drawRoundedRect(r, self.radius, self.radius)
        if self.border and self.width:
            half = self.width / 2
            p.setPen(QPen(QColor(self.border), self.width, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))
            p.setBrush(Qt.NoBrush)
            rad = max(0.0, self.radius - half)
            p.drawRoundedRect(r.adjusted(half, half, -half, -half), rad, rad)


class Text:
    """Text placed like a CSS block: top-left corner, optional width and alignment.

    `key` names a value from Dash.values(); without one the text is a fixed label.
    """

    def __init__(self, x, y, size, text="", key=None, w=None, align="l", color="#d8d8d8",
                 spacing=3.0, line=None):
        self.x, self.y, self.w, self.size = x, y, w, size
        self.text, self.key, self.align, self.color = text, key, align, color
        self.spacing, self.line = spacing, line


def label(x, y, text, w=None, align="l", size=15):
    return Text(x, y, size, text, w=w, align=align, color="#d4d4d4", spacing=0.5)


def value(key, x, y, size, w=None, align="l", color="#d8d8d8", spacing=3.0, line=None):
    return Text(x, y, size, key=key, w=w, align=align, color=color, spacing=spacing, line=line)


def shifted(items, dx, dy):
    """Move a group (children of a bordered CSS box are placed inside the border)."""
    for it in items:
        if isinstance(it, Box):
            it.rect.translate(dx, dy)
        else:
            it.x += dx
            it.y += dy
    return items


class Layout:
    W, H = 800, 507
    SCREEN_Y = 64          # the shift-light bar sits above the screen
    LEDS = 10
    LED_SIZE, LED_GAP = 34, 24
    LED_OFF, LED_OFF_BORDER = "#262626", "#333333"
    FLASH = "#3A7BFF"

    @staticmethod
    def led_color(n):
        return "#2FD14A" if n <= 4 else "#FFC61A" if n <= 7 else "#FF3030"

    pages = {}             # page name -> list of Box / Text in screen coordinates


class Lmp3Layout(Layout):
    """Ligier JS P320 (LMP3); positions from dashes/ligierjsp320.html."""
    B = "#a9a9a9"

    pages = {
        "main": [Box(0, 0, 800, 443, fill="#1b1b1d", border="#9c9c9c", width=3, radius=10)] + shifted([
            Box(12, 10, 301, 94, border=B, width=4),
            label(22, 18, "LAST"),
            value("last", 70, 30, 44, w=232, align="r", color="#3f5bd6"),
            Box(309, 10, 172, 139, border=B, width=4),
            value("gear", 309, 8, 132, w=172, align="c", spacing=0, line=142),
            Box(477, 10, 308, 94, border=B, width=4),
            label(488, 18, "BEST"),
            value("best", 536, 30, 44, w=238, align="r", color="#c44ec4"),
            Box(309, 145, 172, 56, border=B, width=4),
            value("rpm", 309, 148, 38, w=172, align="c"),
            label(28, 132, "FUEL USED"),
            value("fuel_used", 150, 120, 34, w=110, align="r"),
            label(28, 194, "FUEL LAP"),
            value("fuel_lap", 150, 182, 34, w=110, align="r"),
            label(490, 124, "DIFF"),
            value("diff", 560, 116, 34, w=210, align="r"),
            Box(273, 205, 240, 120, border=B, width=4),
            value("tfl", 284, 212, 34, spacing=2),
            value("tfr", 400, 212, 34, w=102, align="r", spacing=2),
            label(273, 253, "Tyre Press", w=240, align="c", size=17),
            value("trl", 284, 276, 34, spacing=2),
            value("trr", 400, 276, 34, w=102, align="r", spacing=2),
            label(600, 206, "SPEED", w=120, align="c"),
            value("speed", 580, 236, 72, w=180, align="c", spacing=2),
            label(22, 346, "OIL P", w=120, align="c"),
            value("oil", 14, 368, 46, w=140, align="c"),
            Box(158, 334, 108, 96, border="#c9c27a", width=4),
            label(158, 344, "TC", w=108, align="c"),
            value("tc", 158, 370, 42, w=108, align="c", color="#e2dd9e", spacing=0),
            Box(314, 334, 168, 84, border="#a3804e", width=4),
            label(314, 344, "RAIN LIGHT", w=168, align="c"),
            value("rain", 314, 366, 36, w=168, align="c"),
            Box(514, 334, 108, 96, border="#c43fc4", width=4),
            label(514, 344, "PPS", w=108, align="c"),
            value("pps", 514, 370, 42, w=108, align="c", color="#d978d9", spacing=0),
            label(648, 346, "WATER T", w=120, align="c"),
            value("water", 640, 368, 46, w=136, align="c"),
        ], 3, 3),   # inside #main's 3 px border

        "pit": [
            Box(0, 0, 800, 443, fill="#2b33b0", radius=10),
            Box(8, 11, 140, 70, fill="#121216", radius=6),
            Box(8, 87, 140, 100, fill="#121216", border="#b08a4a", width=4, radius=6),
            *shifted([label(0, 6, "RAIN LIGHT", w=132, align="c", size=16),
                      value("rain", 0, 32, 38, w=132, align="c", spacing=1)], 12, 91),
            Box(8, 194, 140, 103, fill="#121216", border="#d8d38a", width=4, radius=6),
            *shifted([label(0, 6, "TC MAP", w=132, align="c", size=16),
                      value("tc", 0, 32, 42, w=132, align="c", color="#e8e2a0", spacing=1)], 12, 198),
            Box(156, 11, 146, 138, fill="#121216", radius=6),
            value("gear", 156, 2, 128, w=146, align="c", color="#bdbdbd", spacing=1, line=148),
            Box(310, 11, 314, 138, fill="#121216", radius=6),
            label(322, 18, "SPEED", size=17),
            value("speed", 330, 30, 104, w=276, align="r", color="#d0d0d0", spacing=1, line=112),
            Box(632, 11, 160, 176, fill="#121216", radius=6),
            label(632, 108, "WATER T", w=160, align="c", size=17),
            value("water", 632, 128, 44, w=160, align="c", spacing=1),
            Box(640, 194, 152, 103, fill="#121216", border="#d040d0", width=4, radius=6),
            *shifted([label(0, 6, "PPS MAP", w=144, align="c", size=16),
                      value("pps", 0, 32, 42, w=144, align="c", color="#e070e0", spacing=1)], 644, 198),
            Box(156, 157, 254, 140, fill="#121216", radius=6),
            label(168, 177, "FUEL USED", size=16),
            value("fuel_used", 290, 166, 34, w=108, align="r", spacing=1),
            label(168, 221, "BRAKE BALANCE", size=16),
            value("bias", 300, 210, 34, w=98, align="r", spacing=1),
            label(168, 266, "PEDAL (%)", size=16),
            value("pedal", 300, 255, 34, w=98, align="r", spacing=1),
            Box(418, 157, 206, 140, fill="#121216", radius=6),
            label(418, 164, "Tyre Press", w=206, align="c", size=17),
            value("tfl", 430, 188, 34, spacing=1),
            value("tfr", 520, 188, 34, w=92, align="r", spacing=1),
            value("trl", 430, 242, 34, spacing=1),
            value("trr", 520, 242, 34, w=92, align="r", spacing=1),
            Box(8, 308, 784, 125, fill="#5a61d4", border="#8a90ee", width=3, radius=6),
            Text(11, 311, 60, "PIT LIMIT ACTIVE", w=778, align="c", color="#b9bdf7", spacing=3, line=119),
        ],
    }


LAYOUTS = {"ligierjsp320": Lmp3Layout}
DEFAULT_LAYOUT = Lmp3Layout          # dashes/default.html is the LMP3 dash too


def layout_for(car_path):
    return LAYOUTS.get(car_path or "", DEFAULT_LAYOUT)


# ---- values -------------------------------------------------------------------------
RAIN_ON, RAIN_OFF = "#FF4040", "#3CCF5A"
DIFF_FASTER, DIFF_SLOWER = "#3CCF5A", "#FF4040"


class DashState:
    """Turns a /data-style dict into what's on screen. Equal states draw identically."""

    def __init__(self):
        self.fuel = FuelTracker()

    def reset(self):
        self.fuel.reset()

    def compute(self, d, layout, now):
        """(page, values, colours, leds) for data dict `d`; d=None means waiting for iRacing."""
        if d is None:
            return ("main", WAITING_VALUES, (("rain", "#6cc46c"),), (layout.LED_OFF,) * layout.LEDS, True)
        g = d.get
        rpm = _num(g("Rpms"))
        rpm = 0.0 if not math.isfinite(rpm) else rpm
        gear = g("Gear")
        delta = _num(g("LapDeltaToSessionBestLap"))
        self.fuel.update(_num(g("Fuel")), _num(g("CompletedLaps")))
        rain = g("dcRainLight")
        rain_on = _num(rain) > 0
        vals = {
            "rpm": str(_round(rpm)),
            "gear": "N" if gear in (None, "") else str(gear),
            "speed": fixed(g("Speed"), 0),
            "last": lap_time(g("LastLapTime")),
            "best": lap_time(g("BestLapTime")),
            "diff": (("+" if delta > 0 else "") + f"{delta:.2f}") if math.isfinite(delta) and delta != 0 else "",
            "fuel_used": f"{self.fuel.used:.2f}",
            "fuel_lap": f"{max(0.0, self.fuel.last_lap):.2f}",
            "tfl": fixed(g("TyrePressureFrontLeft"), 1), "tfr": fixed(g("TyrePressureFrontRight"), 1),
            "trl": fixed(g("TyrePressureRearLeft"), 1), "trr": fixed(g("TyrePressureRearRight"), 1),
            "oil": fixed(g("OilPressure"), 1),
            "water": fixed(g("WaterTemperature"), 0),
            "tc": map_value(g("dcTractionControl")),
            "pps": map_value(g("dcThrottleShape")),
            "rain": "-" if rain is None else ("ON" if rain_on else "OFF"),
            "bias": fixed(g("BrakeBias"), 1),
            "pedal": fixed(g("ThrottlePct"), 1),
        }
        colors = {"rain": RAIN_ON if rain_on else RAIN_OFF}
        if vals["diff"]:
            colors["diff"] = DIFF_FASTER if delta < 0 else DIFF_SLOWER
        page = "pit" if _num(g("PitLimiter")) > 0 else "main"
        leds = self._leds(rpm, _num(g("DriverCarSLFirstRPM")), _num(g("DriverCarSLLastRPM")),
                          _num(g("DriverCarSLBlinkRPM")), _num(g("MaxRpm")), layout, now)
        return (page, tuple(sorted(vals.items())), tuple(sorted(colors.items())), leds, False)

    @staticmethod
    def _leds(rpm, first, last, blink, max_rpm, layout, now):
        if not (first > 0 and last > first):                 # iRacing's values not available
            if max_rpm > 0:
                first, last, blink = max_rpm * 0.80, max_rpm * 0.96, max_rpm * 0.98
            else:
                first = last = blink = math.inf
        if not (blink > 0):
            blink = last
        n_leds = layout.LEDS
        flash_on = int(now / 0.12) % 2 == 0
        out = []
        for i in range(n_leds):
            n = i + 1
            if rpm >= blink:
                c = layout.FLASH if flash_on else None
            elif rpm >= first + (last - first) * (n - 1) / (n_leds - 1):
                c = layout.led_color(n)
            else:
                c = None
            out.append(c or layout.LED_OFF)
        return tuple(out)


# ---- the widget -----------------------------------------------------------------------
class NativeDash(QWidget):
    """Draws a Layout scaled to fit, centred, on black. Call show_state(); it repaints
    only when the state differs from what's on screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)     # we paint every pixel: no background fill
        self.layout_cls = DEFAULT_LAYOUT
        self.state = None
        self.debug_lines = None
        self._static = None           # (key, QPixmap) of boxes and labels for the current page
        self._fonts = {}
        self._rects = {}              # (layout, page) -> [(value key, widget QRect)]
        self.paints = 0              # for testing: how many times it actually redrew

    def set_layout(self, layout_cls):
        if layout_cls is not self.layout_cls:
            self.layout_cls = layout_cls
            self._static = None
            self.update()

    def show_state(self, state, debug_lines=None):
        """Repaint only what changed: the boxes whose values changed and/or the shift lights.
        A new page, debug view or the first frame repaints everything."""
        old = self.state
        if state == old and debug_lines == self.debug_lines:
            return
        self.state = state
        whole = (old is None or debug_lines or self.debug_lines
                 or old[0] != state[0] or old[4] != state[4])
        self.debug_lines = debug_lines
        if whole:
            self.update()
            return
        changed = {k for k, v in set(old[1]) ^ set(state[1])} | {k for k, v in set(old[2]) ^ set(state[2])}
        region = QRegion()
        for key, rect in self._value_rects(state[0]):
            if key in changed:
                region = region.united(rect)
        if old[3] != state[3]:
            region = region.united(self._map(QRectF(0, 0, self.layout_cls.W, self.layout_cls.SCREEN_Y)))
        if not region.isEmpty():
            self.update(region)

    def resizeEvent(self, e):
        self._static = None
        self._rects = {}
        super().resizeEvent(e)

    # ---- where each value sits on the widget ------------------------------------------
    def _scale_offset(self):
        L = self.layout_cls
        s = min(self.width() / L.W, self.height() / L.H)
        return s, (self.width() - L.W * s) / 2, (self.height() - L.H * s) / 2

    def _map(self, r):
        """Canvas rect -> widget QRect (rounded outwards, with a little margin)."""
        s, ox, oy = self._scale_offset()
        return QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s) \
            .adjusted(-2, -2, 2, 2).toAlignedRect()

    def _value_rects(self, page):
        key = (self.layout_cls, page)
        rects = self._rects.get(key)
        if rects is None:
            L = self.layout_cls
            rects = []
            for it in L.pages[page]:
                if isinstance(it, Text) and it.key is not None:
                    w = it.w if it.w is not None else it.size * 4      # left-aligned, no width
                    h = it.line or it.size * 1.3
                    r = QRectF(it.x - 4, L.SCREEN_Y + it.y, w + 8 + it.spacing, h)
                    rects.append((it.key, self._map(r)))
            self._rects[key] = rects
        return rects

    # ---- drawing helpers ------------------------------------------------------------
    def _font(self, size, spacing, mono=False):
        key = (size, spacing, mono)
        f = self._fonts.get(key)
        if f is None:
            f = QFont()
            if mono:
                f.setFamilies(["Consolas", "DejaVu Sans Mono", "Courier New"])
            else:
                f.setFamilies(FONT_FAMILIES)
            f.setPixelSize(size)
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
            f.setHintingPreference(QFont.PreferNoHinting)   # it's drawn scaled
            self._fonts[key] = f
        return f

    def _draw_text(self, p, t, text, color):
        if not text:
            return
        p.setFont(self._font(t.size, t.spacing))
        p.setPen(QColor(color))
        fm = p.fontMetrics()
        line = t.line or fm.height()
        w = t.w if t.w is not None else fm.horizontalAdvance(text) + 2
        flags = {"l": Qt.AlignLeft, "c": Qt.AlignHCenter, "r": Qt.AlignRight}[t.align]
        if t.line:
            flags |= Qt.AlignVCenter       # CSS centres the glyphs in an explicit line-height
        else:
            flags |= Qt.AlignTop           # line-height: normal puts the ascent at the top
        rect = QRectF(t.x, t.y, w, line)
        if t.align == "r" and t.spacing:
            rect.adjust(0, 0, t.spacing, 0)   # CSS letter-spacing trails the last letter too
        p.drawText(rect, int(flags) | int(Qt.TextDontClip), text)

    def _transform(self, p):
        L = self.layout_cls
        s = min(self.width() / L.W, self.height() / L.H)
        p.translate((self.width() - L.W * s) / 2, (self.height() - L.H * s) / 2)
        p.scale(s, s)

    def _static_layer(self, page, waiting):
        key = (self.layout_cls, page, waiting, self.size(), self.devicePixelRatioF())
        if self._static and self._static[0] == key:
            return self._static[1]
        dpr = self.devicePixelRatioF()
        pm = QPixmap(QSize(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._transform(p)
        L = self.layout_cls
        p.translate(0, L.SCREEN_Y)
        for it in L.pages[page]:
            if isinstance(it, Box):
                it.draw(p)
            elif it.key is None:
                self._draw_text(p, it, it.text, it.color)
        p.end()
        self._static = (key, pm)
        return pm

    def paintEvent(self, e):
        self.paints += 1
        L = self.layout_cls
        page, vals, colors, leds, waiting = self.state or DashState().compute(None, L, 0)
        dirty = e.region()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._static_layer(page, waiting))     # clipped to the dirty area
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._transform(p)

        # Shift lights.
        if dirty.intersects(self._map(QRectF(0, 0, L.W, L.SCREEN_Y))):
            total = L.LEDS * L.LED_SIZE + (L.LEDS - 1) * L.LED_GAP
            x0, y0 = (L.W - total) / 2, (L.SCREEN_Y - L.LED_SIZE) / 2
            for i, c in enumerate(leds):
                col = QColor(c)
                border = QColor(L.LED_OFF_BORDER) if c == L.LED_OFF else col
                r = QRectF(x0 + i * (L.LED_SIZE + L.LED_GAP), y0, L.LED_SIZE, L.LED_SIZE) \
                    .adjusted(1.5, 1.5, -1.5, -1.5)
                p.setPen(QPen(border, 3))
                p.setBrush(col)
                p.drawEllipse(r)

        # Values (only the ones in the dirty area).
        vals, colors = dict(vals), dict(colors)
        rects = self._value_rects(page)
        p.save()
        p.translate(0, L.SCREEN_Y)
        k = 0
        for it in L.pages[page]:
            if isinstance(it, Text) and it.key is not None:
                if dirty.intersects(rects[k][1]):
                    self._draw_text(p, it, vals.get(it.key, ""), colors.get(it.key, it.color))
                k += 1
        p.restore()
        if waiting:
            p.setFont(self._font(12, 0))
            p.setPen(QColor("#888888"))
            p.drawText(QRectF(0, 0, L.W - 12, L.H - 8), int(Qt.AlignRight | Qt.AlignBottom),
                       "Waiting for iRacing…")

        if self.debug_lines:
            p.fillRect(QRectF(0, 0, L.W, L.H), QColor(0, 0, 0, 235))
            p.setFont(self._font(12, 0, mono=True))
            p.setPen(QColor("#99ff99"))
            p.drawText(QRectF(10, 10, L.W - 20, L.H - 20), int(Qt.AlignLeft | Qt.AlignTop),
                       "\n".join(self.debug_lines))
        p.end()


def debug_lines(d):
    """The debug view: every value the dash reads, as received."""
    lines = ["DEBUG — values received from iRacing (right-click → Debug view to hide)", ""]
    if d is None:
        return lines + ["(no data: iRacing isn't connected)"]
    for k in sorted(d):
        lines.append(f"{k:28s} {d[k]!r}")
    return lines
