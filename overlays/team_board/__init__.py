"""Team pit board: stays on screen and updates once a lap, just after you cross the line,
with what your team would hang over the pit wall:

    P4            GT3
    P3 #22       +1.8   gained 0.3
    P5 #7        -0.9   lost 0.1
    track: #88 ahead 2.6 · #6 behind 1.1
    L12        6 TO GO
    LAST     1:47.412

Between updates nothing moves, the same as a real board. See timing.py for how gaps are
measured.
"""
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QPainter, QPen

from core import winutil
from overlays import base
from overlays.pit_board import PitBoardWindow, _font, _qc
from .timing import DemoBoards, LapTimer, fmt_laptime

BASE_W = 270
PAD = 12
H_POS, H_GAP, H_TRACK, H_LAP, H_LAST = 66, 56, 22, 42, 34


class TeamBoardWindow(PitBoardWindow):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.setWindowTitle("Sim Racing HUD - team pit board")
        self.board = None
        self.flash = 0.0     # 1 -> 0 after an update

    def default_pos(self, w, h):
        g = QGuiApplication.primaryScreen().geometry()
        return g.left() + int(g.width() * 0.03), g.top() + int(g.height() * 0.22)

    def _rows(self):
        c = self.ov.cfg
        rows = [("pos", H_POS), ("ahead", H_GAP), ("behind", H_GAP)]
        if c["show_track"]:
            rows.append(("track", H_TRACK * 2 + 6))
        if c["show_lap"]:
            rows.append(("lap", H_LAP))
        if c["show_last_lap"]:
            rows.append(("last", H_LAST))
        return rows

    def board_size(self):
        s = self.scale()
        return int(BASE_W * s), int((sum(h for _, h in self._rows()) + PAD * 2) * s)

    def paintEvent(self, _):
        c = self.ov.cfg
        s = self.scale()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        W, H = self.width(), self.height()
        op = float(c["opacity"])

        frame = max(2.0, 5 * s)
        rim = QColor(150, 150, 155, int(255 * op))
        if self.flash > 0 and c["flash_on_update"]:
            hl = _qc(c["color_text_hi"], "#ffd400")
            k = self.flash
            rim = QColor(int(150 + (hl.red() - 150) * k), int(150 + (hl.green() - 150) * k),
                         int(155 + (hl.blue() - 155) * k), int(255 * op))
        p.setPen(Qt.NoPen)
        p.setBrush(rim)
        p.drawRoundedRect(QRectF(0, 0, W, H), 7 * s, 7 * s)
        p.setBrush(QColor(8, 8, 8, int(255 * op)))
        p.drawRoundedRect(QRectF(frame, frame, W - 2 * frame, H - 2 * frame), 4 * s, 4 * s)

        x0, x1 = frame + PAD * s, W - frame - PAD * s
        y = PAD * s
        b = self.board
        white = _qc(c["color_text"], "#f5f5f5")
        hi = _qc(c["color_text_hi"], "#ffd400")
        grey = QColor(150, 150, 150)
        good, bad = _qc(c["color_gain"], "#3ddc54"), _qc(c["color_loss"], "#ff3b3b")

        def text(rect, align, t, px, col, bold=True):
            p.setFont(_font(px * s, bold))
            p.setPen(col)
            p.drawText(rect, align, t)

        L, R, VC = Qt.AlignLeft, Qt.AlignRight, Qt.AlignVCenter
        for kind, h in self._rows():
            hh = h * s
            r = QRectF(x0, y, x1 - x0, hh)
            if kind == "pos":
                text(r, L | VC, f"P{b.pos}" if b and b.pos else "P–", 54, hi)
                sub = ""
                if b:
                    sub = (b.class_name + "  " if b.class_name else "") + ("QUALI" if b.qualifying else "")
                text(QRectF(x0, y + 6 * s, x1 - x0, hh / 2), R | VC, sub.strip(), 15, grey)
                if not b:
                    text(QRectF(x0, y + hh / 2, x1 - x0, hh / 2 - 4 * s), R | VC, "after your next lap", 13, grey, False)
            elif kind in ("ahead", "behind"):
                g = getattr(b, kind) if b else None
                sign = "+" if kind == "ahead" else "−"
                if b is None:
                    text(r, R | VC, sign + " –", 44, grey)
                elif g is None:
                    text(r, L | VC, "LEADER" if kind == "ahead" else "LAST", 26, grey)
                else:
                    their_pos = b.pos - 1 if kind == "ahead" else b.pos + 1
                    text(QRectF(x0, y + 4 * s, 110 * s, hh / 2), L | VC, f"P{their_pos} #{g.number}", 16, grey)
                    if g.trend is not None and abs(g.trend) >= 0.05 and c["show_trend"]:
                        up = g.trend > 0
                        text(QRectF(x0, y + hh / 2, 110 * s, hh / 2 - 4 * s), L | VC,
                             ("▲ " if up else "▼ ") + f"{abs(g.trend):.1f}", 15, good if up else bad)
                    if g.laps:
                        big = f"{sign}{g.laps} LAP" + ("S" if g.laps > 1 else "")
                        text(QRectF(x0 + 100 * s, y, x1 - x0 - 100 * s, hh), R | VC, big, 30, white)
                    elif b.qualifying and g.estimated:
                        text(QRectF(x0 + 100 * s, y, x1 - x0 - 100 * s, hh), R | VC, "NO TIME", 26, grey)
                    else:
                        val = f"{sign}{g.seconds:.1f}" if g.seconds < 100 else f"{sign}{g.seconds:.0f}"
                        text(QRectF(x0 + 100 * s, y, x1 - x0 - 100 * s, hh), R | VC,
                             ("~" if g.estimated else "") + val, 44, white)
            elif kind == "track":
                text(QRectF(x0, y, 70 * s, H_TRACK * s), L | VC, "TRACK", 13, grey)
                for k, (row, word) in enumerate(((b.track_ahead if b else None, "ahead"),
                                                 (b.track_behind if b else None, "behind"))):
                    yy = y + k * (H_TRACK + 3) * s
                    rr = QRectF(x0 + 56 * s, yy, x1 - x0 - 56 * s, H_TRACK * s)
                    if row is None:
                        text(rr, L | VC, f"clear {word}", 15, grey, False)
                        continue
                    col = white
                    if row.lap_diff > 0:
                        col = _qc(c["color_lap_ahead"], "#ff7b7b")
                    elif row.lap_diff < 0:
                        col = _qc(c["color_lap_down"], "#6fb4ff")
                    if row.class_color:
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(*row.class_color))
                        p.drawRect(QRectF(rr.left() - 8 * s, yy + 4 * s, 3 * s, H_TRACK * s - 8 * s))
                    text(rr, L | VC, f"#{row.number} {word}", 16, col)
                    text(rr, R | VC, f"{abs(row.gap):.1f}", 18, col)
            elif kind == "lap":
                text(r, L | VC, f"L{b.lap}" if b and b.lap else "L–", 32, white)
                text(r, R | VC, b.remaining if b else "", 22, hi)
            elif kind == "last":
                text(r, L | VC, "LAST", 14, grey)
                text(r, R | VC, fmt_laptime(b.last_lap) if b else "--", 24, white)
            y += hh

        if self.ov.app.layout_mode:
            text(QRectF(0, H - 18 * s, W, 14 * s), Qt.AlignHCenter | VC, "drag · scroll to resize", 10, grey, False)
            p.setPen(QPen(QColor(255, 176, 0), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 7 * s, 7 * s)
        p.end()


class TeamBoardOverlay(base.Overlay):
    id = "team_board"
    title = "Team pit board"
    DEFAULTS = {
        "enabled": True,
        "hotkey": "ctrl+shift+b",
        "show_mode": "always",          # "always" or "after_line" (only for a few seconds, like a real board)
        "show_for_s": 12.0,
        "update_delay_s": 1.0,
        "show_trend": True,
        "show_track": True,
        "show_lap": True,
        "show_last_lap": True,
        "flash_on_update": True,
        "color_text": "#f5f5f5",
        "color_text_hi": "#ffd400",
        "color_gain": "#3ddc54",
        "color_loss": "#ff3b3b",
        "color_lap_ahead": "#ff7b7b",
        "color_lap_down": "#6fb4ff",
        "opacity": 0.92,
        "fade_s": 0.25,
        "scale": 1.0,
        "x": None,
        "y": None,
    }
    VARS = ("PlayerCarIdx", "SessionTime", "SessionLapsRemainEx", "SessionTimeRemain", "LapCompleted",
            "LapLastLapTime", "CarIdxLapDistPct", "CarIdxLapCompleted", "CarIdxClassPosition",
            "CarIdxEstTime", "CarIdxLap", "CarIdxTrackSurface", "CarIdxOnPitRoad",
            "CarIdxBestLapTime", "CarIdxLastLapTime")

    def start(self):
        self.timer = LapTimer()
        self.paused = False
        self.demo = None
        self.preview_until = 0.0
        self.alpha = 0.0
        self.shown_at = -1e9      # when the latest board went out (monotonic)
        self.win = TeamBoardWindow(self)
        self.win.place()

    def apply_settings(self, key=None):
        self.win.place()

    def settings_spec(self):
        return [
            base.check("enabled", "Use the team pit board"),
            base.note("Updates once a lap, just after you cross the line, with what your team would "
                      "put on the board: position, gap to the cars ahead and behind in your class, "
                      "whether you're gaining, the cars around you on track, laps to go and your last lap."),
            base.hotkey("hotkey", "Hide / show hotkey", "Hides it until you press it again or leave iRacing"),
            base.button("Preview for 16 s", self.preview),
            base.header("When it's on screen"),
            base.choice("show_mode", "Show", [("always", "All the time (updates each lap)"),
                                              ("after_line", "Only after the line, like a real board")]),
            base.decimal("show_for_s", "  Shown for", 2, 60, 1, 0, " s", "With 'Only after the line'"),
            base.decimal("update_delay_s", "Update after crossing the line", 0.2, 5, 0.1, 1, " s",
                         "Gives iRacing a moment to update positions and lap times"),
            base.check("flash_on_update", "Flash the frame when it updates"),
            base.header("What's on it"),
            base.check("show_trend", "Gained / lost since the last lap"),
            base.check("show_track", "Cars nearest you on track (any class)"),
            base.check("show_lap", "Lap and laps / time to go"),
            base.check("show_last_lap", "Your last lap time"),
            base.note("Gap to the car behind is from when they crossed the line after you last lap, "
                      "like a real team. '~' means it's an estimate (no line timing yet)."),
            base.header("Look"),
            base.color("color_text_hi", "Position and highlight colour"),
            base.color("color_text", "Text colour"),
            base.color("color_gain", "Gained colour"),
            base.color("color_loss", "Lost colour"),
            base.color("color_lap_ahead", "Track: car a lap up on you"),
            base.color("color_lap_down", "Track: car a lap down"),
            base.percent("opacity", "Board opacity", 20, 100),
            base.decimal("scale", "Size", 0.4, 3, 0.05, 2, " ×", "Or scroll over the board in layout mode"),
            base.decimal("fade_s", "Fade in / out", 0, 1, 0.05, 2, " s"),
            base.note("Move it in layout mode: drag the board, scroll to resize."),
        ]

    # ---- actions ---------------------------------------------------------------
    def toggle(self):
        self.paused = not self.paused
        self._sync_tray()

    def preview(self):
        self.preview_until = time.monotonic() + 16.0
        self.demo = DemoBoards(time.monotonic())

    def hotkeys(self):
        return {"team.toggle": ("hotkey", self.toggle)}

    def build_tray(self, menu):
        self.act_toggle = QAction("", menu, triggered=lambda *_: self.toggle())
        menu.addAction(self.act_toggle)
        menu.addAction(QAction("Team pit board preview (16 s)", menu, triggered=lambda *_: self.preview()))
        self._sync_tray()

    def _sync_tray(self):
        if getattr(self, "act_toggle", None):
            self.act_toggle.setText("Show team pit board" if self.paused else "Hide team pit board")

    def on_layout_mode(self, on):
        self.demo = DemoBoards(time.monotonic()) if on else None
        self.win.update()

    def on_session_end(self):
        self.timer.reset()
        self.win.board = None
        if self.paused:
            self.paused = False
            self._sync_tray()

    # ---- every frame -------------------------------------------------------------
    def _new_board(self, board, now):
        self.win.board = board
        self.shown_at = now
        self.win.flash = 1.0

    def tick(self, frame, ctx):
        c = self.cfg
        want = False
        real = None
        if frame.connected and not ctx.demo:
            # Keep timing every car even while hidden, so the next board is right.
            real = self.timer.update(frame.vars, frame.session, float(c["update_delay_s"]))
        simulated = ctx.layout_mode or ctx.now < self.preview_until or (ctx.demo and c["enabled"])
        if simulated:
            if self.demo is None:
                self.demo = DemoBoards(ctx.now)
            board, new = self.demo.read(ctx.now)
            if new:
                self._new_board(board, ctx.now)
            want = True
        else:
            if self.demo is not None:          # back from a preview: show the real board again
                self.demo = None
                self.win.board = self.timer.board
            if real is not None:
                self._new_board(real, ctx.now)
            want = bool(c["enabled"] and not self.paused and frame.driving and ctx.visible)
            if want and c["show_mode"] == "after_line":
                want = ctx.now - self.shown_at <= float(c["show_for_s"])

        if self.win.flash > 0:
            self.win.flash = max(0.0, self.win.flash - ctx.dt / 1.2)
            self.win.update()

        fade = max(1e-3, float(c["fade_s"]))
        self.alpha = min(1.0, self.alpha + ctx.dt / fade) if want else max(0.0, self.alpha - ctx.dt / fade)
        if self.alpha > 0:
            self.win.setWindowOpacity(self.alpha)
            if not self.win.isVisible():
                self.win.place()
                self.win.show()
                winutil.keep_topmost(self.win)
        elif self.win.isVisible():
            self.win.hide()

    def keep_on_top(self):
        winutil.keep_topmost(self.win)

    def shutdown(self):
        if getattr(self, "win", None):
            self.win.hide()
