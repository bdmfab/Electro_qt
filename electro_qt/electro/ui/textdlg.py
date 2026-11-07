"""Text properties: font, height, colour."""
from __future__ import annotations
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QFontComboBox, QDoubleSpinBox,
                               QComboBox, QDialogButtonBox)
from .items import PALETTE, aci_color


def fill_color_combo(combo: QComboBox, current=None):
    """'By layer' (None) followed by the palette."""
    combo.addItem("By layer", None)
    for n, (name, _) in PALETTE.items():
        pm = QPixmap(14, 14); pm.fill(aci_color(n))
        combo.addItem(QIcon(pm), name, n)
    i = combo.findData(current)
    combo.setCurrentIndex(max(0, i))


class TextPropsDialog(QDialog):
    def __init__(self, parent, font="", height=0.12, color=None):
        super().__init__(parent)
        self.setWindowTitle("Text properties")
        self.font_box = QFontComboBox()
        if font:
            self.font_box.setCurrentFont(QFont(font))
        self.height = QDoubleSpinBox()
        self.height.setDecimals(3); self.height.setRange(0.02, 5.0); self.height.setSingleStep(0.01)
        self.height.setValue(height); self.height.setSuffix(" in")
        self.color = QComboBox()
        fill_color_combo(self.color, color)
        form = QFormLayout()
        form.addRow("Font", self.font_box)
        form.addRow("Height", self.height)
        form.addRow("Color", self.color)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        return self.font_box.currentFont().family(), self.height.value(), self.color.currentData()
