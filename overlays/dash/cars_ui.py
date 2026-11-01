"""Settings -> Dash -> Dash per car: which dash layout (or none) each car gets.

Cars appear in the list the first time you drive them, so there's no car path to type.
"Every other car" covers cars set to Default, including ones not driven yet.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .native import DASH_LAYOUTS, NO_DASH, USE_DEFAULT


def dash_options():
    """[(id, text)] for every dash the user can pick, "No dash" first."""
    return [(NO_DASH, "No dash")] + [(k, cls.NAME) for k, cls in DASH_LAYOUTS.items()]


def dash_name(dash_id):
    return dict(dash_options()).get(dash_id, "No dash")


class CarDashList(QWidget):
    def __init__(self, ov):
        super().__init__()
        self.ov = ov
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.addWidget(QLabel("Every other car:"))
        self.default_box = QComboBox()
        self.default_box.setToolTip("Cars set to Default, and cars you haven't driven yet")
        self.default_box.currentIndexChanged.connect(self._default_changed)
        top.addWidget(self.default_box, 1)
        lay.addLayout(top)

        self.rows = QWidget()
        self.grid = QGridLayout(self.rows)
        self.grid.setContentsMargins(0, 6, 0, 0)
        self.grid.setColumnStretch(0, 1)
        lay.addWidget(self.rows)

        hint = QLabel("A car is added here the first time you drive it. "
                      "The dash switches as soon as you change a car's setting.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self._filling = False
        self.refresh()

    # ---- building --------------------------------------------------------------
    def refresh(self):
        """Rebuild from config (called on open, after a change and when a new car shows up)."""
        self._filling = True
        cfg = self.ov.cfg
        opts = dash_options()
        self.default_box.clear()
        for _, text in opts:
            self.default_box.addItem(text)
        ids = [k for k, _ in opts]
        cur = cfg.get("default_dash")
        self.default_box.setCurrentIndex(ids.index(cur) if cur in ids else 0)

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cars = cfg.get("cars") or {}
        if not cars:
            empty = QLabel("No cars yet: drive one and it appears here.")
            empty.setStyleSheet("color: gray;")
            self.grid.addWidget(empty, 0, 0, 1, 3)
        current = self.ov.car_path
        default_text = dash_name(cfg.get("default_dash"))
        row_opts = [(USE_DEFAULT, f"Default ({default_text})")] + opts
        row_ids = [k for k, _ in row_opts]
        for r, path in enumerate(sorted(cars, key=lambda p: (cars[p].get("name") or p).lower())):
            entry = cars[path]
            name = entry.get("name") or path
            lab = QLabel(f"<b>{name}</b>  <span style='color:gray'>(driving now)</span>"
                         if path == current else name)
            lab.setToolTip(f"iRacing car path: {path}")
            box = QComboBox()
            for _, text in row_opts:
                box.addItem(text)
            choice = entry.get("dash", USE_DEFAULT)
            box.setCurrentIndex(row_ids.index(choice) if choice in row_ids else 0)
            box.currentIndexChanged.connect(lambda i, p=path, ids=row_ids: self._car_changed(p, ids[i]))
            rm = QPushButton("Remove")
            rm.setToolTip("Take it off the list (it comes back with Default the next time you drive it)")
            if path == current:
                rm.setEnabled(False)
                rm.setToolTip("You're in this car now")
            rm.clicked.connect(lambda *_, p=path: self._remove(p))
            self.grid.addWidget(lab, r, 0)
            self.grid.addWidget(box, r, 1)
            self.grid.addWidget(rm, r, 2)
        self._filling = False

    # ---- changes ---------------------------------------------------------------
    def _default_changed(self, i):
        if self._filling:
            return
        self.ov.cfg["default_dash"] = dash_options()[i][0]
        self.ov.cars_changed()
        QTimer.singleShot(0, self.refresh)    # the "Default (…)" texts follow

    def _car_changed(self, path, dash_id):
        if self._filling:
            return
        self.ov.cfg["cars"][path]["dash"] = dash_id
        self.ov.cars_changed()

    def _remove(self, path):
        self.ov.cfg["cars"].pop(path, None)
        self.ov.cars_changed()
        QTimer.singleShot(0, self.refresh)
