"""Telling the user about updates, like a normal app.

- Checks GitHub shortly after starting and every few hours.
- When there's a new version it waits until you're off track, then shows one tray notification.
  Click it (or the tray menu's "Update available" entry) for what's new and three choices:
  Update now / Remind me later / Skip this version.
- Update now downloads the installer, closes the HUD, updates and starts it again.
  Settings live in %APPDATA%\\SimRacingHUD, so they're kept.
"""
import threading
import traceback
import webbrowser

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QSystemTrayIcon

from . import paths, updater
from .version import VERSION

FIRST_CHECK_MS = 20 * 1000
EVERY_MS = 6 * 60 * 60 * 1000


class UpdateManager(QObject):
    _checked = Signal(object, bool)       # release or None, manual
    _check_failed = Signal(str, bool)
    _progress = Signal(int, int)
    _downloaded = Signal(str)
    _download_failed = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pending = None          # a newer Release we know about
        self.announced = False       # notification already shown for it
        self.busy = False
        self.dialog_open = False
        self._cancel = False
        self.progress_dlg = None
        self.action = None           # tray menu entry, set by the app

        self._checked.connect(self._on_checked)
        self._check_failed.connect(self._on_check_failed)
        self._progress.connect(self._on_progress)
        self._downloaded.connect(self._on_downloaded)
        self._download_failed.connect(self._on_download_failed)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.check(manual=False))
        if not app.demo:
            QTimer.singleShot(FIRST_CHECK_MS, lambda: self.check(manual=False))
            self.timer.start(EVERY_MS)

    @property
    def g(self):
        return self.app.config["general"]

    # ---- checking ---------------------------------------------------------------
    def check(self, manual=True):
        if self.busy or (not manual and not self.g.get("check_updates", True)):
            return
        self.busy = True

        def work():
            try:
                self._checked.emit(updater.fetch_latest(), manual)
            except Exception as e:
                self._check_failed.emit(str(e), manual)
        threading.Thread(target=work, daemon=True, name="update-check").start()

    def _on_checked(self, rel, manual):
        self.busy = False
        if rel is None or not updater.is_newer(rel.version):
            if manual:
                self._info("You're up to date", f"Sim Racing HUD {VERSION} is the latest version.")
            return
        if not manual and rel.version == self.g.get("skip_version"):
            return
        self.pending = rel
        self._refresh_action()
        print(f"Update available: {rel.version}")
        if manual:
            self.announced = True
            self.show_dialog()
        else:
            self.announced = False   # new, or the periodic re-check after "Remind me later"

    def _on_check_failed(self, err, manual):
        self.busy = False
        print("Update check failed:", err)
        if manual:
            self._info("Couldn't check for updates", f"There was a problem reaching GitHub:\n{err}")

    def _refresh_action(self):
        if self.action is not None:
            self.action.setVisible(self.pending is not None)
            if self.pending:
                self.action.setText(f"Update available: {self.pending.version}…")

    # ---- the notification ---------------------------------------------------------
    def tick(self, on_track):
        """Called every frame. The notification only appears when you're not driving."""
        if self.pending and not self.announced and not on_track and not self.dialog_open:
            self.announced = True
            self.app.notify_update(f"Sim Racing HUD {self.pending.version} is available",
                                   "Click here to see what's new and update.")

    # ---- the dialog -------------------------------------------------------------
    def show_dialog(self):
        rel = self.pending
        if rel is None or self.dialog_open:
            return
        self.dialog_open = True
        try:
            box = QMessageBox()
            box.setWindowTitle("Sim Racing HUD update")
            box.setWindowIcon(self.app.icon)
            box.setIcon(QMessageBox.Information)
            box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            box.setText(f"<b>Version {rel.version} is available.</b><br>You have {VERSION}.")
            notes = rel.notes or "No notes for this version."
            if len(notes) > 1200:
                notes = notes[:1200] + "…"
            box.setInformativeText("What's new:\n" + notes)
            can_install = paths.FROZEN and bool(rel.installer_url)
            now = box.addButton("Update now" if can_install else "Open download page",
                                QMessageBox.AcceptRole)
            later = box.addButton("Remind me later", QMessageBox.RejectRole)
            skip = box.addButton("Skip this version", QMessageBox.DestructiveRole)
            box.setDefaultButton(now)
            box.setEscapeButton(later)
            box.exec()
            clicked = box.clickedButton()
        finally:
            self.dialog_open = False

        if clicked is now:
            if can_install:
                self.start_download()
            else:
                webbrowser.open(rel.page)
        elif clicked is skip:
            self.g["skip_version"] = rel.version
            self.app.save_config_soon()
            self.pending = None
            self._refresh_action()
        # Remind me later: the next periodic check shows the notification again.

    # ---- downloading and installing -------------------------------------------------
    def start_download(self):
        rel = self.pending
        self._cancel = False
        dlg = QProgressDialog(f"Downloading Sim Racing HUD {rel.version}…", "Cancel", 0, 100)
        dlg.setWindowTitle("Sim Racing HUD update")
        dlg.setWindowIcon(self.app.icon)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumDuration(0)
        dlg.canceled.connect(self._on_cancel)
        dlg.setValue(0)
        dlg.show()
        self.progress_dlg = dlg

        def work():
            try:
                path = updater.download(rel, lambda d, t: self._progress.emit(d, t),
                                        lambda: self._cancel)
                self._downloaded.emit(path)
            except InterruptedError:
                pass
            except Exception as e:
                traceback.print_exc()
                self._download_failed.emit(str(e))
        threading.Thread(target=work, daemon=True, name="update-download").start()

    def _on_cancel(self):
        self._cancel = True

    def _on_progress(self, done, total):
        if self.progress_dlg and total:
            self.progress_dlg.setValue(int(done * 100 / total))

    def _close_progress(self):
        if self.progress_dlg:
            self.progress_dlg.canceled.disconnect(self._on_cancel)
            self.progress_dlg.close()
            self.progress_dlg = None

    def _on_downloaded(self, path):
        self._close_progress()
        try:
            print("Starting the installer:", path)
            updater.run_installer(path)
        except Exception as e:
            self._on_download_failed(f"Couldn't start the installer: {e}")
            return
        self.app.qt.quit()          # the installer updates the files and starts the HUD again

    def _on_download_failed(self, err):
        self._close_progress()
        box = QMessageBox(QMessageBox.Warning, "Sim Racing HUD update",
                          f"The update couldn't be downloaded:\n{err}\n\n"
                          "You can try again later, or download it from the releases page.")
        box.setWindowIcon(self.app.icon)
        page = box.addButton("Open releases page", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is page:
            webbrowser.open(updater.RELEASES_PAGE)

    def _info(self, title, text):
        box = QMessageBox(QMessageBox.Information, title, text)
        box.setWindowIcon(self.app.icon)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.exec()
