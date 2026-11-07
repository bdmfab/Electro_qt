"""Text styles dialog: named styles (font, height, color, justification)."""
from __future__ import annotations
import copy
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget, QPushButton,
                               QFontComboBox, QDoubleSpinBox, QComboBox, QDialogButtonBox, QInputDialog,
                               QMessageBox)
from .. import model as m
from .textdlg import fill_color_combo


class TextStylesDialog(QDialog):
    def __init__(self, parent, styles):
        super().__init__(parent)
        self.setWindowTitle("Text styles")
        self.styles = copy.deepcopy(styles)
        self.list = QListWidget()
        self.font = QFontComboBox()
        self.height = QDoubleSpinBox(); self.height.setDecimals(3); self.height.setRange(0.02, 5.0)
        self.height.setSingleStep(0.01); self.height.setSuffix(" in")
        self.color = QComboBox(); fill_color_combo(self.color, None)
        self.align = QComboBox()
        for t, v in (("Left", "left"), ("Center", "center"), ("Right", "right")):
            self.align.addItem(t, v)
        form = QFormLayout()
        for lab, w in (("Font", self.font), ("Height", self.height), ("Color", self.color), ("Justify", self.align)):
            form.addRow(lab, w)
        new, dele = QPushButton("New..."), QPushButton("Delete")
        new.clicked.connect(self._new); dele.clicked.connect(self._delete)
        side = QVBoxLayout(); side.addLayout(form); side.addStretch()
        btns = QHBoxLayout(); btns.addWidget(new); btns.addWidget(dele)
        left = QVBoxLayout(); left.addWidget(self.list); left.addLayout(btns)
        row = QHBoxLayout(); row.addLayout(left); row.addLayout(side)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(row); lay.addWidget(bb)
        self._cur = None
        self.list.currentTextChanged.connect(self._select)
        self._fill()

    def _fill(self, pick=None):
        self.list.blockSignals(True); self.list.clear()
        self.list.addItems(list(self.styles)); self.list.blockSignals(False)
        names = list(self.styles)
        self.list.setCurrentRow(names.index(pick) if pick in names else 0)
        self._select(self.list.currentItem().text())

    def _store(self):
        if self._cur in self.styles:
            st = self.styles[self._cur]
            st.font = self.font.currentFont().family() if self.font.currentFont().family() else ""
            st.height, st.color, st.align = self.height.value(), self.color.currentData(), self.align.currentData()

    def _select(self, name):
        self._store()
        if not name or name not in self.styles:
            return
        self._cur = name
        st = self.styles[name]
        if st.font:
            self.font.setCurrentFont(QFont(st.font))
        self.height.setValue(st.height)
        self.color.setCurrentIndex(max(0, self.color.findData(st.color)))
        self.align.setCurrentIndex(max(0, self.align.findData(st.align)))

    def _new(self):
        name, ok = QInputDialog.getText(self, "New text style", "Name:")
        name = name.strip()
        if ok and name and name not in self.styles:
            self._store()
            src = self.styles[self._cur]
            self.styles[name] = m.TextStyle(name, src.font, src.height, src.color, src.align)
            self._cur = None
            self._fill(name)

    def _delete(self):
        if self._cur == "Default":
            QMessageBox.information(self, "Text styles", "The Default style cannot be deleted."); return
        self.styles.pop(self._cur, None); self._cur = None
        self._fill("Default")

    def accept(self):
        self._store()
        super().accept()

    def result_styles(self):
        return self.styles
