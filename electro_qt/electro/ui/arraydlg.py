"""Array dialog: linear (rows x columns) or polar, with optional text numbering."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QTabWidget, QWidget, QSpinBox,
                               QDoubleSpinBox, QCheckBox, QDialogButtonBox, QLabel)


def _dsb(val, lo=-999.0, hi=999.0, dec=3, suffix=" in"):
    b = QDoubleSpinBox(); b.setDecimals(dec); b.setRange(lo, hi); b.setValue(val); b.setSuffix(suffix)
    return b


class ArrayDialog(QDialog):
    def __init__(self, parent, row_pitch=0.35):
        super().__init__(parent)
        self.setWindowTitle("Array")
        self.tabs = QTabWidget()
        lin = QWidget(); f = QFormLayout(lin)
        self.rows = QSpinBox(); self.rows.setRange(1, 200); self.rows.setValue(1)
        self.cols = QSpinBox(); self.cols.setRange(1, 200); self.cols.setValue(3)
        self.dx = _dsb(1.0); self.dy = _dsb(row_pitch)
        f.addRow("Rows", self.rows); f.addRow("Columns", self.cols)
        f.addRow("Column spacing (X)", self.dx); f.addRow("Row spacing (Y, up is +)", self.dy)
        pol = QWidget(); g = QFormLayout(pol)
        self.count = QSpinBox(); self.count.setRange(2, 500); self.count.setValue(4)
        self.angle = _dsb(360.0, -360.0, 360.0, 2, " deg")
        self.cx = _dsb(0.0); self.cy = _dsb(1.0)
        self.relative = QCheckBox("Center is an offset from the selection's center")
        self.relative.setChecked(True)
        self.rotate = QCheckBox("Rotate the copies"); self.rotate.setChecked(True)
        g.addRow("Total items", self.count); g.addRow("Fill angle", self.angle)
        g.addRow("Center X", self.cx); g.addRow("Center Y", self.cy)
        g.addRow(self.relative); g.addRow(self.rotate)
        self.tabs.addTab(lin, "Linear"); self.tabs.addTab(pol, "Polar")
        self.inc = QCheckBox("Increment the trailing number in text, per copy")
        self.step = QSpinBox(); self.step.setRange(-999, 999); self.step.setValue(1)
        h = QFormLayout(); h.addRow(self.inc); h.addRow("Step", self.step)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addWidget(self.tabs); lay.addLayout(h)
        lay.addWidget(QLabel("Example: TB09 becomes TB10, TB11, ... (zero padding kept)."))
        lay.addWidget(bb)

    def values(self):
        base = {"inc": self.inc.isChecked(), "step": self.step.value()}
        if self.tabs.currentIndex() == 0:
            return {**base, "mode": "linear", "rows": self.rows.value(), "cols": self.cols.value(),
                    "dx": self.dx.value(), "dy": self.dy.value()}
        return {**base, "mode": "polar", "count": self.count.value(), "angle": self.angle.value(),
                "cx": self.cx.value(), "cy": self.cy.value(), "relative": self.relative.isChecked(),
                "rotate": self.rotate.isChecked()}
