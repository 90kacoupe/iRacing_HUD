"""Settings window, built from each overlay's settings_spec(). Changes apply and save straight away."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QKeySequenceEdit, QLabel, QPushButton, QScrollArea,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from core import winutil
from core.hotkeys import from_qt, parse_hotkey, to_qt


class HotkeyEdit(QWidget):
    changed = Signal(str)

    def __init__(self, text):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QKeySequenceEdit(QKeySequence(to_qt(text)) if text else QKeySequence())
        try:
            self.edit.setMaximumSequenceLength(1)
        except Exception:
            pass
        self.edit.setToolTip("Click, then press the key combination")
        self.edit.editingFinished.connect(self._done)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        self.warn = QLabel("")
        self.warn.setStyleSheet("color: #d33;")
        lay.addWidget(self.edit, 1)
        lay.addWidget(clear)
        lay.addWidget(self.warn)

    def _done(self):
        text = from_qt(self.edit.keySequence().toString(QKeySequence.PortableText))
        if text and not parse_hotkey(text):
            self.warn.setText("can't use that key")
            return
        self.warn.setText("")
        self.changed.emit(text)

    def _clear(self):
        self.edit.clear()
        self.warn.setText("")
        self.changed.emit("")


class SettingsWindow(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.Window)
        self.app = app
        self.setWindowTitle("Sim Racing HUD settings" + (" (demo)" if app.demo else ""))
        self.setWindowIcon(app.icon)
        self.resize(560, 680)

        tabs = QTabWidget()
        tabs.addTab(self._page("general", app.general_spec()), "General")
        for ov in app.overlays:
            title = ov.title + (" (stopped)" if ov.failed else "")
            try:
                spec = ov.settings_spec()
            except Exception:
                spec = [{"type": "note", "label": "This overlay's settings couldn't be shown (see hud.log)."}]
            tabs.addTab(self._page(ov.id, spec), title)
        tabs.addTab(self._page("server", app.server_spec()), "Network")

        bottom = QHBoxLayout()
        self.layout_btn = QPushButton()
        self.layout_btn.clicked.connect(lambda: app.set_layout_mode(not app.layout_mode))
        folder = QPushButton("Open settings folder")
        folder.setToolTip("config.json and hud.log")
        from core.paths import DATA_DIR
        folder.clicked.connect(lambda: winutil.open_path(DATA_DIR))
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(self.layout_btn)
        bottom.addWidget(folder)
        bottom.addStretch(1)
        bottom.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs, 1)
        hint = QLabel("Changes apply straight away and are saved to config.json.")
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        lay.addLayout(bottom)
        self.layout_changed()

    def layout_changed(self):
        self.layout_btn.setText("Finish layout mode" if self.app.layout_mode else "Layout mode (move / resize)")

    # ---- building rows ------------------------------------------------------------
    def _page(self, section, spec):
        inner = QWidget()
        form = QFormLayout(inner)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        for item in spec:
            try:
                self._row(form, section, item)
            except Exception as e:
                form.addRow(QLabel(f"(couldn't show {item.get('label')}: {e})"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _row(self, form, section, item):
        t = item["type"]
        label = item.get("label", "")
        tip = item.get("tip", "")
        cfg = self.app.config[section]
        key = item.get("key")

        def changed(value, kind=t):
            cfg[key] = value
            self.app.setting_changed(section, key, kind)

        if t == "header":
            lab = QLabel(f"<b>{label}</b>")
            lab.setContentsMargins(0, 10, 0, 0)
            form.addRow(lab)
            return
        if t == "note":
            lab = QLabel(label)
            lab.setWordWrap(True)
            lab.setStyleSheet("color: gray;")
            form.addRow(lab)
            return
        if t == "button":
            w = QPushButton(label)
            w.clicked.connect(lambda *_: item["fn"]())
            w.setToolTip(tip)
            form.addRow(w)
            return
        if t in ("bool", "toggle"):
            w = QCheckBox(label)
            w.setChecked(bool(item["get"]() if t == "toggle" else cfg.get(key)))
            if t == "toggle":
                w.toggled.connect(lambda on: item["set"](on))
            else:
                w.toggled.connect(lambda on: changed(bool(on)))
            w.setToolTip(tip)
            form.addRow(w)
            return

        if t == "int":
            w = QSpinBox()
            w.setRange(item["lo"], item["hi"])
            w.setSingleStep(item["step"])
            w.setSuffix(item["suffix"])
            w.setValue(int(cfg.get(key) or 0))
            w.valueChanged.connect(lambda v: changed(int(v)))
        elif t == "float":
            w = QDoubleSpinBox()
            w.setDecimals(item["decimals"])
            w.setRange(item["lo"], item["hi"])
            w.setSingleStep(item["step"])
            w.setSuffix(item["suffix"])
            w.setValue(float(cfg.get(key) or 0))
            w.valueChanged.connect(lambda v: changed(float(v)))
        elif t == "pct":
            w = QSpinBox()
            w.setRange(item["lo"], item["hi"])
            w.setSuffix(" %")
            w.setValue(int(round(float(cfg.get(key) or 0) * 100)))
            w.valueChanged.connect(lambda v: changed(v / 100.0))
        elif t == "choice":
            w = QComboBox()
            values = [v for v, _ in item["options"]]
            for v, text in item["options"]:
                w.addItem(text)
            cur = cfg.get(key)
            w.setCurrentIndex(values.index(cur) if cur in values else 0)
            w.currentIndexChanged.connect(lambda i: changed(values[i]))
        elif t == "color":
            w = QPushButton()
            w.setFixedWidth(90)

            def paint(c, btn=w):
                btn.setStyleSheet(f"background: {c}; border: 1px solid #777; border-radius: 3px; min-height: 22px;")

            def pick(*_, btn=w):
                c = QColorDialog.getColor(QColor(cfg.get(key)), self, label)
                if c.isValid():
                    paint(c.name())
                    changed(c.name())
            paint(cfg.get(key) or "#ffffff")
            w.clicked.connect(pick)
        elif t == "hotkey":
            w = HotkeyEdit(cfg.get(key) or "")
            w.changed.connect(lambda text: changed(text))
        else:
            return
        w.setToolTip(tip)
        form.addRow(label, w)
