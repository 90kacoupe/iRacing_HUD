"""Replica in-car dash, drawn natively (native.py) in an always-on-top window.

The same dash also exists as an HTML page per car in dashes/, served by the app's local
web server (/dash, reading /data), for a browser, phone or separate dash screen. The
overlay window doesn't use those pages, so no web engine runs while you drive.
"""
import webbrowser

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget, QMenu

from core import winutil
from core.server import json_response, redirect
from overlays import base
from .native import DashState, DemoDash, NativeDash, debug_lines, layout_for
from .payload import VARS, DASHES_DIR, build_data, build_payload, dash_file_for


class GrabLayer(QWidget):
    """Invisible layer over the page: drag to move, scroll to resize, right-click for a menu."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.drag = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = e.globalPosition().toPoint() - self.win.pos()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.win.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.drag = None
            self.win.remember()

    def mouseDoubleClickEvent(self, e):
        if self.win.ov.app.layout_mode:
            self.win.ov.app.set_layout_mode(False)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.win.scale_by(1.05 ** steps)

    def contextMenuEvent(self, e):
        ov = self.win.ov
        m = QMenu(self)
        m.addAction("Finish moving" if ov.app.layout_mode else "Layout mode (move / resize)",
                    lambda: ov.app.set_layout_mode(not ov.app.layout_mode))
        m.addAction("Debug view on / off", ov.toggle_debug)
        m.addAction("Hide dash", ov.toggle)
        m.addSeparator()
        m.addAction("Settings…", ov.app.open_settings)
        m.exec(e.globalPos())

    def paintEvent(self, _):
        if not self.win.ov.app.layout_mode:
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        pen = QPen(QColor(255, 176, 0), 3, Qt.DashLine)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        p.setPen(QColor(255, 255, 255))
        f = QFont()
        f.setPointSize(max(9, min(16, self.width() // 40)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter,
                   "Drag to move  ·  Scroll to resize\nDouble-click when done")
        p.end()


class DashWindow(QWidget):
    def __init__(self, overlay):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.ov = overlay
        self.setWindowTitle("Sim Racing HUD - dash")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.dash = NativeDash(self)
        self.aspect = None
        self.grab_layer = GrabLayer(self)
        self.restore()
        self.set_layout(self.dash.layout_cls)

    # ---- geometry ----------------------------------------------------------------
    def restore(self):
        c = self.ov.cfg
        w, h = int(c.get("width") or 800), int(c.get("height") or 507)
        x, y = c.get("x"), c.get("y")
        rect = QRect(int(x or 0), int(y or 0), w, h)
        on_screen = any(s.availableGeometry().intersects(rect.adjusted(40, 40, -40, -40))
                        for s in QGuiApplication.screens())
        if x is None or y is None or not on_screen:
            g = QGuiApplication.primaryScreen().availableGeometry()
            rect.moveCenter(g.center())
        self.setGeometry(rect)

    def remember(self):
        g = self.geometry()
        self.ov.cfg.update(x=g.x(), y=g.y(), width=g.width(), height=g.height())
        self.ov.app.save_config_soon()

    def scale_by(self, f):
        w = max(200, int(self.width() * f))
        h = int(w * self.aspect) if self.aspect else max(120, int(self.height() * f))
        self.resize(w, h)
        self.remember()

    def resizeEvent(self, e):
        self.dash.setGeometry(self.rect())
        self.grab_layer.setGeometry(self.rect())
        self.grab_layer.raise_()
        super().resizeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        winutil.add_ex_style(self, winutil.WS_EX_NOACTIVATE | winutil.WS_EX_TOOLWINDOW)

    # ---- which car's dash ------------------------------------------------------------
    def set_layout(self, layout_cls):
        """Use this car's dash and keep the window the dash's shape (no empty bars)."""
        self.dash.set_layout(layout_cls)
        self.aspect = layout_cls.H / layout_cls.W
        want = int(self.width() * self.aspect)
        if abs(self.height() - want) > 2:
            self.resize(self.width(), want)
            self.remember()


class DashOverlay(base.Overlay):
    id = "dash"
    title = "Dash"
    DEFAULTS = {"enabled": True, "hotkey": "ctrl+shift+d", "x": None, "y": None, "width": 800, "height": 507}
    VARS = VARS

    def start(self):
        self.override = None    # "hide" / "show" from the hotkey, until pressed again or iRacing closes
        self.debug = False
        self.shown = False
        self.car_path = None
        self.state = DashState()
        self.demo = None        # DemoDash in demo mode / layout mode
        s = self.app.server
        s.route("/data", self._route_data)
        s.route("/dash", self._route_dash)
        s.route("/car", self._route_car)
        s.route("/vars", self._route_vars)
        s.mount("/dashes/", DASHES_DIR)
        self.win = DashWindow(self)

    # ---- web routes (run on the server thread) -------------------------------------
    def _route_data(self, query):
        frame = self.app.telemetry.latest()
        if not frame.connected:
            return json_response(b'{"connected": false}', 503)
        return json_response(build_payload(frame, self.app.config["general"]["units"]))

    def _route_dash(self, query):
        car = self.app.telemetry.latest().session.get("car_path")
        return redirect("/dashes/" + dash_file_for(car) + ("?" + query if query else ""))

    def _route_car(self, query):
        car = self.app.telemetry.latest().session
        return json_response({"car_path": car.get("car_path"), "car_name": car.get("car_name"),
                              "dash_file": "dashes/" + dash_file_for(car.get("car_path"))})

    def _route_vars(self, query):
        return json_response(self.app.telemetry.latest().session.get("all_vars", []))

    # ---- page --------------------------------------------------------------------
    def page_url(self):
        """The HTML version of the dash, for a browser or another device."""
        return self.app.server.url("/dash") + ("?demo" if self.app.demo else "")

    def set_debug(self, on):
        self.debug = on

    def toggle_debug(self):
        self.set_debug(not self.debug)

    # ---- actions -------------------------------------------------------------------
    def toggle(self):
        self.override = "hide" if self.shown else "show"
        self._sync_tray()

    def reset_position(self):
        self.cfg.update(x=None, y=None, width=800, height=int(800 * (self.win.aspect or 507 / 800)))
        self.win.restore()
        self.win.remember()

    def hotkeys(self):
        return {"dash.toggle": ("hotkey", self.toggle)}

    def build_tray(self, menu):
        self.act_toggle = QAction("Hide dash", menu, triggered=lambda *_: self.toggle())
        menu.addAction(self.act_toggle)

    def _sync_tray(self):
        if getattr(self, "act_toggle", None):
            self.act_toggle.setText("Hide dash" if self.shown else "Show dash")

    def on_session_end(self):
        self.override = None

    def on_layout_mode(self, on):
        self.win.grab_layer.update()

    def settings_spec(self):
        return [
            base.check("enabled", "Use the dash"),
            base.hotkey("hotkey", "Hide / show hotkey",
                        "Hides the dash until you press it again or leave iRacing. "
                        "Outside a session it shows the dash, handy for positioning."),
            base.note("Move it by dragging, resize with the mouse wheel. Right-click it for more."),
            base.button("Reset size and position", self.reset_position),
            base.button("Debug view on / off", self.toggle_debug),
            base.header("Browser and dash-screen pages"),
            base.note("The overlay draws the dash itself. The same dash is also available as a web "
                      "page (one per car in the dashes folder, named after iRacing's car path; "
                      "default.html for every other car) for a browser, phone or dash screen."),
            base.button("Open the dashes folder", lambda: winutil.open_path(DASHES_DIR)),
            base.button("Show the current car's path", lambda: webbrowser.open(self.app.server.url("/car"))),
            base.button("Open the dash in a browser", lambda: webbrowser.open(self.page_url())),
        ]

    # ---- every frame -------------------------------------------------------------
    def tick(self, frame, ctx):
        car = frame.session.get("car_path")
        if car != self.car_path:                       # new car: its dash, fresh fuel figures
            self.car_path = car
            self.win.set_layout(layout_for(car))
            self.state.reset()

        want = bool(self.cfg["enabled"] and (
            ctx.layout_mode or self.override == "show" or (self.override != "hide" and ctx.visible)))
        if want:
            # Only does any work while the dash is on screen.
            if ctx.demo or (ctx.layout_mode and not frame.connected):
                self.demo = self.demo or DemoDash(ctx.now)
                data = self.demo.read(ctx.now)
            else:
                self.demo = None
                data = build_data(frame, self.app.config["general"]["units"]) if frame.connected else None
            self.win.dash.show_state(self.state.compute(data, self.win.dash.layout_cls, ctx.now),
                                     debug_lines(data) if self.debug else None)
        if want != self.shown:
            self.shown = want
            if want:
                self.win.show()
                winutil.keep_topmost(self.win)
            else:
                self.win.hide()
            self._sync_tray()

    def keep_on_top(self):
        winutil.keep_topmost(self.win)

    def shutdown(self):
        if getattr(self, "win", None):
            self.win.hide()
