"""Pit board: a relative (time gaps to the cars around you) that only appears when you need it.

It shows while the pit limiter is on, when you go off track or lose control, or when you're
stopped on track (after a spin, say),
and stays a few seconds after so you can judge the gap as you rejoin. The rest of the time
it's off the screen, like a real car with no relative box.

Drawn like a pit board held over the wall: black board, bold white figures. Cars ahead on
top, you in the middle, cars behind below. A car close behind turns amber, then red.
"""
import time

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from core import winutil
from overlays import base
from .relative import (REASON_LIMITER, REASON_OFF_TRACK, REASON_PEEK, REASON_PIT_ROAD, REASON_SPIN,
                       REASON_STOPPED, DemoRelative, Trigger, build_relative)

BASE_W = 360          # board width at 100 % size
ROW_H = 30
HEAD_H = 34
PAD = 10
FONT_FAMILIES = ["Bahnschrift SemiCondensed", "Bahnschrift", "Arial Narrow", "DIN Condensed", "Arial"]

HEADINGS = {REASON_LIMITER: "PIT LIMITER", REASON_STOPPED: "STOPPED",
            REASON_PIT_ROAD: "PIT LANE", REASON_PEEK: "RELATIVE",
            REASON_OFF_TRACK: "OFF TRACK", REASON_SPIN: "SPIN"}


def _font(px, bold=True):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(max(6, int(px)))
    f.setBold(bold)
    return f


def _qc(hex_text, fallback="#ffffff"):
    c = QColor(hex_text)
    return c if c.isValid() else QColor(fallback)


class PitBoardWindow(QWidget):
    def __init__(self, overlay):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.ov = overlay
        self.setWindowTitle("Sim Racing HUD - pit board")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.data = None       # (ahead, me, behind)
        self.reason = None
        self.drag = None
        winutil.add_ex_style(self, winutil.WS_EX_NOACTIVATE | winutil.WS_EX_TOOLWINDOW)

    # ---- size and place ----------------------------------------------------------
    def scale(self):
        return max(0.4, float(self.ov.cfg["scale"]))

    def board_size(self):
        c = self.ov.cfg
        s = self.scale()
        rows = int(c["cars_ahead"]) + int(c["cars_behind"]) + 1
        return int(BASE_W * s), int((HEAD_H + rows * ROW_H + PAD * 2) * s)

    def default_pos(self, w, h):
        g = QGuiApplication.primaryScreen().geometry()
        return g.center().x() - w // 2, g.top() + int(g.height() * 0.12)

    def place(self):
        c = self.ov.cfg
        w, h = self.board_size()
        x, y = c.get("x"), c.get("y")
        if x is None or y is None:
            x, y = self.default_pos(w, h)
        rect = QRectF(int(x), int(y), w, h).toRect()
        if not any(s.geometry().intersects(rect.adjusted(30, 30, -30, -30)) for s in QGuiApplication.screens()):
            rect.moveTopLeft(QPoint(*self.default_pos(w, h)))
        self.setGeometry(rect)
        self.update()

    def remember(self):
        self.ov.cfg.update(x=self.x(), y=self.y())
        self.ov.app.save_config_soon()

    # ---- mouse: drag to move, wheel to resize (never takes focus) ----------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.drag = None
            self.remember()

    def mouseDoubleClickEvent(self, e):
        if self.ov.app.layout_mode:
            self.ov.app.set_layout_mode(False)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.ov.cfg["scale"] = round(max(0.4, min(3.0, self.scale() * 1.05 ** steps)), 3)
            self.ov.app.save_config_soon()
            self.place()

    def contextMenuEvent(self, e):
        app = self.ov.app
        m = QMenu(self)
        m.addAction("Finish moving" if app.layout_mode else "Layout mode (move / resize)",
                    lambda: app.set_layout_mode(not app.layout_mode))
        m.addAction("Hide " + self.ov.title.lower(), self.ov.toggle)
        m.addSeparator()
        m.addAction("Settings…", app.open_settings)
        m.exec(e.globalPos())

    # ---- drawing -------------------------------------------------------------------
    def paintEvent(self, _):
        c = self.ov.cfg
        s = self.scale()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        W, H = self.width(), self.height()

        # The board: black with a brushed-metal frame.
        frame = max(2.0, 4 * s)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(150, 150, 155, int(255 * c["opacity"])))
        p.drawRoundedRect(QRectF(0, 0, W, H), 6 * s, 6 * s)
        p.setBrush(QColor(8, 8, 8, int(255 * c["opacity"])))
        p.drawRoundedRect(QRectF(frame, frame, W - 2 * frame, H - 2 * frame), 4 * s, 4 * s)

        x0, x1 = PAD * s + frame, W - PAD * s - frame
        y = PAD * s

        # Heading: why it's showing.
        p.setFont(_font(22 * s))
        p.setPen(_qc(c["color_heading"], "#ffd400"))
        heading = HEADINGS.get(self.reason, "RELATIVE")
        p.drawText(QRectF(x0, y, x1 - x0, HEAD_H * s), Qt.AlignLeft | Qt.AlignVCenter, heading)
        if self.ov.app.layout_mode:
            p.setFont(_font(11 * s, bold=False))
            p.setPen(QColor(200, 200, 200))
            p.drawText(QRectF(x0, y, x1 - x0, HEAD_H * s), Qt.AlignRight | Qt.AlignVCenter,
                       "drag · scroll to resize")
        y += HEAD_H * s

        if not self.data:
            p.setFont(_font(16 * s, bold=False))
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRectF(x0, y, x1 - x0, ROW_H * s), Qt.AlignLeft | Qt.AlignVCenter, "No timing yet")
            p.end()
            return

        ahead, me, behind = self.data
        n_ahead, n_behind = int(c["cars_ahead"]), int(c["cars_behind"])
        rows = [None] * (n_ahead - len(ahead)) + list(ahead) + [me] + list(behind) + \
            [None] * (n_behind - len(behind))
        for r in rows:
            if r is not None:
                self._row(p, r, x0, x1, y, s)
            y += ROW_H * s
        if self.ov.app.layout_mode:
            p.setPen(QPen(QColor(255, 176, 0), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 6 * s, 6 * s)
        p.end()

    def _row(self, p, r, x0, x1, y, s):
        c = self.ov.cfg
        h = ROW_H * s
        if r.is_me:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 38))
            p.drawRect(QRectF(x0 - 4 * s, y + 1 * s, x1 - x0 + 8 * s, h - 2 * s))
        # Class colour stripe (multi-class).
        if c["show_class_color"] and r.class_color:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*r.class_color))
            p.drawRect(QRectF(x0, y + 5 * s, 4 * s, h - 10 * s))
        x = x0 + 10 * s

        dim = r.in_pit or r.off_track
        white = QColor(245, 245, 245) if not dim else QColor(140, 140, 140)
        name_col = white
        if r.lap_diff > 0:
            name_col = _qc(c["color_lap_ahead"], "#ff7b7b")
        elif r.lap_diff < 0:
            name_col = _qc(c["color_lap_down"], "#6fb4ff")

        p.setFont(_font(17 * s))
        p.setPen(QColor(170, 170, 170) if not dim else QColor(110, 110, 110))
        if c["show_position"]:
            p.drawText(QRectF(x, y, 40 * s, h), Qt.AlignLeft | Qt.AlignVCenter, f"P{r.pos}" if r.pos else "")
            x += 40 * s
        p.setPen(white)
        p.drawText(QRectF(x, y, 48 * s, h), Qt.AlignLeft | Qt.AlignVCenter, f"#{r.number}")
        x += 50 * s

        gap_w = 78 * s
        tag_w = 40 * s
        name_w = max(10.0, x1 - gap_w - tag_w - x)
        p.setFont(_font(17 * s, bold=r.is_me))
        p.setPen(name_col)
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(x, y, name_w, h), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(r.name, Qt.ElideRight, name_w))

        tag = "PIT" if r.in_pit else "OFF" if r.off_track else ""
        if tag:
            p.setFont(_font(12 * s))
            p.setPen(QColor(255, 176, 0))
            p.drawText(QRectF(x1 - gap_w - tag_w, y, tag_w, h), Qt.AlignCenter, tag)

        if not r.is_me:
            gap_col = white
            if r.gap < 0 and not r.in_pit:          # coming up behind you
                if -r.gap <= float(c["danger_s"]):
                    gap_col = _qc(c["color_danger"], "#ff2a2a")
                elif -r.gap <= float(c["caution_s"]):
                    gap_col = _qc(c["color_caution"], "#ffa000")
            p.setFont(_font(22 * s))
            p.setPen(gap_col)
            text = f"{abs(r.gap):.1f}" if abs(r.gap) < 100 else f"{abs(r.gap):.0f}"
            p.drawText(QRectF(x1 - gap_w, y, gap_w, h), Qt.AlignRight | Qt.AlignVCenter, text)


class PitBoardOverlay(base.Overlay):
    id = "pit_board"
    title = "Pit-lane relative"
    DEFAULTS = {
        "enabled": True,
        "hotkey": "ctrl+shift+p",       # hide / show the pit board
        "peek_hotkey": "",              # show it for a few seconds on demand (off by default)
        "peek_s": 6.0,
        "on_limiter": True,
        "on_stopped": True,
        "on_pit_road": False,
        "on_off_track": True,
        "off_track_for_s": 1.0,
        "on_lost_control": True,
        "slide_deg": 35.0,
        "slide_for_s": 0.25,
        "stopped_kph": 3.0,
        "stopped_for_s": 0.7,
        "skip_grid": True,
        "linger_s": 4.0,
        "cars_ahead": 3,
        "cars_behind": 3,
        "show_position": True,
        "show_class_color": True,
        "caution_s": 4.0,
        "danger_s": 2.0,
        "color_heading": "#ffd400",
        "color_caution": "#ffa000",
        "color_danger": "#ff2a2a",
        "color_lap_ahead": "#ff7b7b",
        "color_lap_down": "#6fb4ff",
        "opacity": 0.92,
        "fade_s": 0.2,
        "scale": 1.0,
        "x": None,
        "y": None,
    }
    VARS = ("PlayerCarIdx", "Speed", "EngineWarnings", "OnPitRoad", "SessionState",
            "CarIdxLapDistPct", "CarIdxEstTime", "CarIdxLap", "CarIdxTrackSurface",
            "CarIdxOnPitRoad", "CarIdxClassPosition", "PlayerTrackSurface", "VelocityX", "VelocityY",
            "Gear")

    def start(self):
        self.trigger = Trigger()
        self.paused = False
        self.preview_until = 0.0
        self.demo = None
        self.alpha = 0.0
        self.last_data = 0.0
        self.win = PitBoardWindow(self)
        self.win.place()

    # ---- settings --------------------------------------------------------------
    def apply_settings(self, key=None):
        self.win.place()

    def settings_spec(self):
        return [
            base.check("enabled", "Use the pit-lane relative"),
            base.note("A relative that only appears when you need it: on the pit limiter, off track, "
                      "after losing control, or stopped on track. The rest of the time there's no "
                      "relative on screen."),
            base.hotkey("hotkey", "Hide / show hotkey", "Hides it until you press it again or leave iRacing"),
            base.hotkey("peek_hotkey", "Quick look hotkey",
                        "Shows the pit board for a few seconds, like asking your engineer for gaps. "
                        "Not set by default, to keep it realistic."),
            base.decimal("peek_s", "Quick look lasts", 1, 30, 1, 0, " s"),
            base.button("Preview for 8 s", self.preview),
            base.header("When it appears"),
            base.check("on_limiter", "Pit limiter on"),
            base.check("on_off_track", "Off track (all four wheels off)",
                       "Two wheels over the line or on a kerb doesn't count, same as iRacing's 1x"),
            base.decimal("off_track_for_s", "Off track for at least", 0, 5, 0.1, 1, " s",
                         "Ignores a quick corner cut. Raise it if it still pops up when you clip a corner"),
            base.check("on_lost_control", "Lost control (big slide or spin)",
                       "Shows straight away in a spin, even if you stay on the track"),
            base.decimal("slide_deg", "Counts as lost control at", 15, 90, 5, 0, "° sideways",
                         "How far the car points away from where it's going. Normal hard driving "
                         "stays well under 20°"),
            base.decimal("slide_for_s", "Sliding for at least", 0, 2, 0.05, 2, " s"),
            base.check("on_stopped", "Stopped on track (after a spin, off at the side…)"),
            base.decimal("stopped_kph", "Counts as stopped below", 0.5, 30, 0.5, 1, " km/h"),
            base.decimal("stopped_for_s", "Stopped for at least", 0, 5, 0.1, 1, " s",
                         "So it doesn't pop up when you're only slow for a moment"),
            base.check("skip_grid", "Not while waiting on the grid",
                       "Ignores being stopped before the green flag"),
            base.check("on_pit_road", "Anywhere on pit road, even with the limiter off"),
            base.decimal("linger_s", "Keep showing after", 0, 20, 0.5, 1, " s",
                         "After the limiter goes off or you move away, so you can see the gap while you rejoin"),
            base.header("What it shows"),
            base.number("cars_ahead", "Cars ahead", 0, 8),
            base.number("cars_behind", "Cars behind", 0, 8),
            base.check("show_position", "Class position"),
            base.check("show_class_color", "Class colour stripe"),
            base.decimal("caution_s", "Car behind turns amber within", 0, 15, 0.5, 1, " s"),
            base.decimal("danger_s", "Car behind turns red within", 0, 10, 0.5, 1, " s"),
            base.color("color_danger", "  Red"),
            base.color("color_caution", "  Amber"),
            base.color("color_lap_ahead", "Name colour: a lap up on you"),
            base.color("color_lap_down", "Name colour: a lap down"),
            base.color("color_heading", "Heading colour"),
            base.header("Look"),
            base.percent("opacity", "Board opacity", 20, 100),
            base.decimal("scale", "Size", 0.4, 3, 0.05, 2, " ×", "Or scroll over the board in layout mode"),
            base.decimal("fade_s", "Fade in / out", 0, 1, 0.05, 2, " s"),
            base.note("Move it in layout mode: drag the board, scroll to resize."),
        ]

    # ---- actions ---------------------------------------------------------------
    def toggle(self):
        """Hide until pressed again or iRacing closes (same as the other overlays' hotkeys)."""
        self.paused = not self.paused
        self._sync_tray()

    def peek(self):
        self.trigger.peek(time.monotonic(), float(self.cfg["peek_s"]))

    def preview(self):
        self.preview_until = time.monotonic() + 8.0
        self.demo = DemoRelative(time.monotonic())

    def hotkeys(self):
        return {"pit.toggle": ("hotkey", self.toggle), "pit.peek": ("peek_hotkey", self.peek)}

    def build_tray(self, menu):
        self.act_toggle = QAction("", menu, triggered=lambda *_: self.toggle())
        menu.addAction(self.act_toggle)
        menu.addAction(QAction("Pit-lane relative preview (8 s)", menu, triggered=lambda *_: self.preview()))
        self._sync_tray()

    def _sync_tray(self):
        if getattr(self, "act_toggle", None):
            self.act_toggle.setText("Show pit-lane relative" if self.paused else "Hide pit-lane relative")

    def on_layout_mode(self, on):
        self.demo = DemoRelative(time.monotonic()) if on else None
        self.win.update()

    def on_session_end(self):
        self.trigger.reset()
        if self.paused:
            self.paused = False
            self._sync_tray()

    # ---- every frame -------------------------------------------------------------
    def tick(self, frame, ctx):
        c = self.cfg
        n_a, n_b = int(c["cars_ahead"]), int(c["cars_behind"])
        want, data, reason = False, None, None

        if ctx.layout_mode or ctx.now < self.preview_until or (ctx.demo and c["enabled"]):
            if self.demo is None:
                self.demo = DemoRelative(ctx.now)
            data, reason = self.demo.read(ctx.now, n_a, n_b)
            want = ctx.layout_mode or ctx.now < self.preview_until or int((ctx.now - self.demo.t0) // 6) % 3 != 2
        elif c["enabled"] and not self.paused and frame.driving and ctx.visible:
            want, reason = self.trigger.update(frame.vars, c, ctx.now)
            if want:
                data = build_relative(frame.vars, frame.session, n_a, n_b)
        else:
            self.trigger.reset()

        # Fade, then hide the window once it's fully gone (it shows again without taking focus).
        fade = max(1e-3, float(c["fade_s"]))
        self.alpha = min(1.0, self.alpha + ctx.dt / fade) if want else max(0.0, self.alpha - ctx.dt / fade)
        if want:
            self.win.data, self.win.reason = data, reason
            if ctx.now - self.last_data > 0.1:      # ~10 updates a second is plenty for gaps
                self.last_data = ctx.now
                self.win.update()
        if self.alpha > 0:
            self.win.setWindowOpacity(self.alpha)
            if not self.win.isVisible():
                self.win.show()
                winutil.keep_topmost(self.win)
        elif self.win.isVisible():
            self.win.hide()

    def keep_on_top(self):
        winutil.keep_topmost(self.win)

    def shutdown(self):
        if getattr(self, "win", None):
            self.win.hide()
