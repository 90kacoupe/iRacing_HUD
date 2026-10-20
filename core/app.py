"""The app: one telemetry reader, one tray icon, one settings window, every overlay."""
import os
import sys
import time
import traceback
import urllib.request

from PySide6 import QtWebEngineWidgets  # noqa: F401  (must be imported before QApplication exists)
from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as cfgmod
from . import paths, winutil
from .hotkeys import GlobalHotkeys, pretty
from .server import HudServer, json_response
from .telemetry import DemoTelemetry, IRacingTelemetry
from .update_ui import UpdateManager
from .version import VERSION
from overlays import base, load_overlay_classes

APP_DIR = paths.APP_DIR
CONFIG_PATH = paths.CONFIG_PATH
FPS = 60

DEFAULTS = {
    "general": {
        "show_only_when_driving": True,   # hidden in the garage, menus and replays
        "hide_delay_s": 1.0,              # seconds off track before hiding, so it doesn't flicker
        "units": "auto",                  # "auto" follows iRacing; or "metric" / "imperial"
        "layout_hotkey": "ctrl+shift+e",
        "settings_hotkey": "",
        "check_updates": True,            # look for a new version on GitHub now and then
        "skip_version": "",               # a version the user chose to skip
    },
    "server": {
        "allow_network": False,           # True: open the dash from a phone / tablet / dash screen
        "port": 8765,
    },
}


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 176, 0))
    p.drawRoundedRect(QRectF(4, 12, 10, 40), 5, 5)
    p.setBrush(QColor(255, 40, 40))
    p.drawRoundedRect(QRectF(50, 12, 10, 40), 5, 5)
    p.setBrush(QColor(40, 44, 52))
    p.drawRoundedRect(QRectF(19, 18, 26, 28), 5, 5)
    p.setBrush(QColor(47, 209, 74))
    p.drawRoundedRect(QRectF(23, 22, 18, 5), 2, 2)
    p.end()
    return QIcon(pm)


class HudApp(QObject):
    hotkey_pressed = Signal(str)
    hotkey_failed = Signal(object)
    settings_requested = Signal()

    def __init__(self, qt, config, demo=False):
        super().__init__()
        self.qt = qt
        self.config = config
        self.demo = demo
        self.layout_mode = False
        self.settings_win = None
        self.icon = make_icon()
        self.qt.setWindowIcon(self.icon)

        classes, load_errors = load_overlay_classes()
        self.overlays = [cls(self) for cls in classes]
        for ov in self.overlays:
            self.config[ov.id] = cfgmod.merge(ov.DEFAULTS, self.config.get(ov.id, {}))

        # Telemetry: one reader for everything.
        names = set()
        for ov in self.overlays:
            names |= set(ov.VARS)
        self.telemetry = DemoTelemetry() if demo else IRacingTelemetry(names)

        # Web server (dash pages, /data, and /show for a second launch).
        srv = self.config["server"]
        port = int(srv["port"]) + (1 if demo else 0)
        self.server = HudServer("0.0.0.0" if srv["allow_network"] else "127.0.0.1", port)
        self.server.route("/show", self._route_show)
        self.settings_requested.connect(self.open_settings)

        self.save_timer = QTimer(singleShot=True, interval=500)
        self.save_timer.timeout.connect(self.save_config)

        self.server_ok = self.server.start()     # overlays can add routes after it starts

        self.err_counts = {}
        for ov in self.overlays:
            self.call(ov, "start")

        self.updates = UpdateManager(self)
        self._build_tray()
        if load_errors:
            self.notify("An overlay didn't load", "See hud.log. The other overlays are running.")
        if self.telemetry.error:
            self.notify("No live data", self.telemetry.error)
        if not self.server_ok:
            self.notify("Dash can't start", self.server.error)

        self.hotkeys = GlobalHotkeys(self.hotkey_pressed.emit, self.hotkey_failed.emit)
        self.hotkey_pressed.connect(self._on_hotkey)
        self.hotkey_failed.connect(self._on_hotkey_failed)
        self.rebind_hotkeys()

        self.visible = False
        self.off_since = None
        self.was_connected = False
        self.last = time.monotonic()
        self.last_top = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / FPS))
        qt.aboutToQuit.connect(self._quitting)
        print("Sim Racing HUD running" + (" (demo)" if demo else "") +
              (f". Dash at {self.server.url('/dash')}" if self.server_ok else ""))

    # ---- keeping one overlay's problems away from the others ------------------------
    def call(self, ov, method, *args):
        if ov.failed:
            return None
        try:
            result = getattr(ov, method)(*args)
            if method == "tick":
                self.err_counts[ov.id] = 0
            return result
        except Exception:
            n = self.err_counts.get(ov.id, 0) + 1
            self.err_counts[ov.id] = n
            if n <= 3:
                print(f"[{ov.id}] error in {method}:")
                traceback.print_exc()
            if method == "start" or n >= 30:
                ov.failed = True
                try:
                    ov.shutdown()
                except Exception:
                    pass
                self.notify(f"{ov.title} stopped", "It hit an error (see hud.log). "
                            "The other overlays keep running.")
            return None

    # ---- tray -------------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.icon)
        menu = QMenu()
        self.act_update = QAction("Update available…", menu, triggered=lambda *_: self.updates.show_dialog())
        self.act_update.setVisible(False)
        menu.addAction(self.act_update)
        self.updates.action = self.act_update
        menu.addAction(QAction("Settings…", menu, triggered=lambda *_: self.open_settings()))
        self.act_layout = QAction("Layout mode (move / resize)", menu, checkable=True,
                                  triggered=lambda on: self.set_layout_mode(on))
        menu.addAction(self.act_layout)
        for ov in self.overlays:
            if ov.failed:
                continue
            menu.addSeparator()
            try:
                ov.build_tray(menu)
            except Exception:
                traceback.print_exc()
        menu.addSeparator()
        menu.addAction(QAction("Check for updates", menu, triggered=lambda *_: self.updates.check(manual=True)))
        menu.addAction(QAction("Quit", menu, triggered=lambda *_: self.qt.quit()))
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(f"Sim Racing HUD {VERSION}" + (" (demo)" if self.demo else ""))
        self._last_note_is_update = False
        self.tray.messageClicked.connect(self._message_clicked)
        self.tray.activated.connect(
            lambda reason: self.open_settings() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        self._menu = menu

    def notify_update(self, title, text):
        """The 'new version' notification. Clicking it opens the update dialog."""
        print(f"{title}: {text}")
        if getattr(self, "tray", None):
            self._last_note_is_update = True
            self.tray.showMessage(title, text, self.icon, 15000)

    def _message_clicked(self):
        if self._last_note_is_update:
            self.updates.show_dialog()

    def notify(self, title, text):
        print(f"{title}: {text}")
        self._last_note_is_update = False
        tray = getattr(self, "tray", None)
        if tray and QSystemTrayIcon.supportsMessages():
            tray.showMessage(title, text or "", QSystemTrayIcon.Warning, 8000)
        else:
            self._pending_notes = getattr(self, "_pending_notes", []) + [(title, text)]
            QTimer.singleShot(1500, self._flush_notes)

    def _flush_notes(self):
        for title, text in getattr(self, "_pending_notes", []):
            if getattr(self, "tray", None):
                self.tray.showMessage(title, text or "", QSystemTrayIcon.Warning, 8000)
        self._pending_notes = []

    # ---- hotkeys ----------------------------------------------------------------
    def _app_hotkeys(self):
        g = self.config["general"]
        return {"app.layout": (g["layout_hotkey"], lambda: self.set_layout_mode(not self.layout_mode)),
                "app.settings": (g["settings_hotkey"], self.open_settings)}

    def rebind_hotkeys(self):
        bindings, self.hotkey_actions = {}, {}
        for name, (text, fn) in self._app_hotkeys().items():
            bindings[name], self.hotkey_actions[name] = text, (None, fn)
        for ov in self.overlays:
            if ov.failed:
                continue
            for name, (key, fn) in ov.hotkeys().items():
                bindings[name], self.hotkey_actions[name] = ov.cfg.get(key, ""), (ov, fn)
        self.hotkey_texts = bindings
        self.hotkeys.set(bindings)

    def _on_hotkey(self, name):
        ov, fn = self.hotkey_actions.get(name, (None, None))
        if fn is None or (ov and ov.failed):
            return
        try:
            fn()
        except Exception:
            traceback.print_exc()

    def _on_hotkey_failed(self, failed):
        lines = [f"{pretty(text)} {why}" for _, text, why in failed]
        self.notify("Hotkey not set", "\n".join(lines) + "\nPick another one in Settings.")

    # ---- settings ---------------------------------------------------------------
    def general_spec(self):
        return [
            base.toggle("Start with Windows", winutil.startup_installed, self._set_startup,
                        "Waits quietly in the tray; overlays only appear while you drive"),
            base.check("show_only_when_driving", "Only show overlays while driving",
                       "Hidden in the garage, menus and replays. Off: shown while iRacing is running."),
            base.decimal("hide_delay_s", "Hide delay", 0, 10, 0.5, 1, " s",
                         "How long you need to be off track before overlays hide"),
            base.choice("units", "Units", [("auto", "Same as iRacing"), ("metric", "Metric"),
                                           ("imperial", "Imperial")]),
            base.header("Hotkeys"),
            base.hotkey("layout_hotkey", "Layout mode (move / resize)"),
            base.hotkey("settings_hotkey", "Open settings"),
            base.note("Each overlay's own hotkeys are on its tab. Hotkeys work while iRacing has focus."),
            base.header("Updates"),
            base.note(f"You have version {VERSION}."),
            base.check("check_updates", "Tell me when there's a new version",
                       "Checks now and then. The notification waits until you're off track."),
            base.button("Check for updates now", lambda: self.updates.check(manual=True)),
        ]

    def server_spec(self):
        return [
            base.check("allow_network", "Let other devices open the dash",
                       "For a phone, tablet or dash screen on your network. Takes effect after a restart."),
            base.number("port", "Port", 1024, 65535, tip="Takes effect after a restart"),
            base.note("Restart the HUD (Quit from the tray, then Start HUD.bat) after changing these."),
        ]

    def _set_startup(self, on):
        if on:
            winutil.remove_old_entries()
            winutil.install_startup()
        else:
            winutil.remove_startup()

    def setting_changed(self, section, key, kind):
        self.save_config_soon()
        if kind == "hotkey":
            self.rebind_hotkeys()
            return
        targets = self.overlays if section in ("general", "server") else \
            [ov for ov in self.overlays if ov.id == section]
        for ov in targets:
            self.call(ov, "apply_settings", key)

    def open_settings(self):
        from ui.settings import SettingsWindow
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self)
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    def save_config_soon(self):
        self.save_timer.start()

    def save_config(self):
        cfgmod.save(CONFIG_PATH, self.config)

    def set_layout_mode(self, on):
        self.layout_mode = bool(on)
        self.act_layout.setChecked(self.layout_mode)
        for ov in self.overlays:
            self.call(ov, "on_layout_mode", self.layout_mode)
        if self.settings_win:
            self.settings_win.layout_changed()

    def _route_show(self, query):
        self.settings_requested.emit()     # queued onto the Qt thread
        return json_response({"ok": True})

    # ---- every frame --------------------------------------------------------------
    def _update_visibility(self, frame, now):
        g = self.config["general"]
        want = frame.driving if g["show_only_when_driving"] else frame.connected
        if want:
            self.visible, self.off_since = True, None
        elif self.visible:
            if not frame.connected:
                self.visible, self.off_since = False, None
            else:
                self.off_since = self.off_since or now
                if now - self.off_since >= float(g["hide_delay_s"]):
                    self.visible, self.off_since = False, None
        if self.was_connected and not frame.connected:
            for ov in self.overlays:
                self.call(ov, "on_session_end")
        self.was_connected = frame.connected

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        frame = self.telemetry.latest()
        self._update_visibility(frame, now)
        ctx = base.Context(now, dt, self.visible, self.layout_mode, self.demo)
        for ov in self.overlays:
            self.call(ov, "tick", frame, ctx)
        self.updates.tick(frame.driving or self.visible)
        if now - self.last_top > 2.0:
            self.last_top = now
            for ov in self.overlays:
                self.call(ov, "keep_on_top")

    def _quitting(self):
        self.save_timer.stop()
        self.save_config()
        for ov in self.overlays:
            if not ov.failed:
                try:
                    ov.shutdown()
                except Exception:
                    pass
        self.server.stop()


def run(demo=False):
    paths.ensure_data_dir()
    defaults = DEFAULTS
    config = cfgmod.load(CONFIG_PATH, defaults)

    # Only one copy (it starts with Windows, and Start HUD.bat may be clicked too).
    # A second launch just opens the running copy's settings. Demo mode has its own slot.
    if winutil.already_running("Local\\SimRacingHUD" + ("_demo" if demo else "")):
        port = int(config["server"]["port"]) + (1 if demo else 0)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/show", timeout=2).read()
            print("The HUD is already running; opened its settings.")
        except Exception:
            print("The HUD is already running (see the tray icon).")
        return 0

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    qt = QApplication.instance() or QApplication(sys.argv)
    qt.setApplicationName("Sim Racing HUD")
    qt.setQuitOnLastWindowClosed(False)
    app = HudApp(qt, config, demo=demo)
    if not os.path.exists(CONFIG_PATH):
        app.save_config()
    return qt.exec()
