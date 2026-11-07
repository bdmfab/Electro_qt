"""Colour standards (multiline presets): a named pattern such as "480 VAC" with, for
each wire, a label (L1, L2, L3, N, PE), the layer it is drawn on and its colour."""
from __future__ import annotations
import dataclasses
from collections import OrderedDict
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QGridLayout, QLabel,
                               QListWidget, QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                               QDialogButtonBox, QMessageBox)
from .. import model as m
from .items import PALETTE, aci_color


def _swatch(n):
    pm = QPixmap(14, 14); pm.fill(aci_color(n)); return QIcon(pm)


class PresetDialog(QDialog):
    def __init__(self, parent, presets, layer_names):
        super().__init__(parent)
        self.setWindowTitle("Color standards (multiline presets)")
        self.resize(720, 400)
        self.entries = [dataclasses.replace(p, layers=list(p.layers), colors=list(p.colors),
                                            labels=list(p.labels)) for p in presets.values()]
        self._row, self._loading = -1, False

        self.list = QListWidget()
        add, rem = QPushButton("Add"), QPushButton("Delete")
        add.clicked.connect(self.on_add); rem.clicked.connect(self.on_delete)
        left = QVBoxLayout(); left.addWidget(self.list)
        row = QHBoxLayout(); row.addWidget(add); row.addWidget(rem); left.addLayout(row)

        self.name = QLineEdit()
        self.count = QSpinBox(); self.count.setRange(2, 4)
        self.spacing = QDoubleSpinBox(); self.spacing.setDecimals(3); self.spacing.setRange(0.0, 5.0)
        self.spacing.setSingleStep(0.025); self.spacing.setSpecialValueText("Sheet row pitch")
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Wires", self.count)
        form.addRow("Spacing", self.spacing)

        grid = QGridLayout()
        for c, t in enumerate(("", "Label", "Layer", "Color")):
            grid.addWidget(QLabel(t), 0, c)
        self.labels, self.layers, self.colors, self.rowlabels = [], [], [], []
        for i in range(4):
            rl = QLabel("Top / left wire" if i == 0 else f"Wire {i + 1}")
            lab = QLineEdit(); lab.setMaximumWidth(70)
            lay = QComboBox(); lay.setEditable(True); lay.addItems(layer_names)
            col = QComboBox()
            for n, (nm, _) in PALETTE.items():
                col.addItem(_swatch(n), nm, n)
            for c, w in enumerate((rl, lab, lay, col)):
                grid.addWidget(w, i + 1, c)
            self.rowlabels.append(rl); self.labels.append(lab); self.layers.append(lay); self.colors.append(col)
        autoname = QPushButton("Name layers from preset name")
        autoname.setToolTip('e.g. "480 VAC" + L1 -> layer "480 VAC L1"')
        autoname.clicked.connect(self.on_autoname)
        note = QLabel("Layers that do not exist are created with these colors the first time you draw.")
        note.setWordWrap(True)
        right = QVBoxLayout(); right.addLayout(form); right.addLayout(grid)
        right.addWidget(autoname); right.addWidget(note); right.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        top = QHBoxLayout(); top.addLayout(left, 1); top.addLayout(right, 3)
        root = QVBoxLayout(self); root.addLayout(top); root.addWidget(bb)

        self.count.valueChanged.connect(self._enable_rows)
        self.list.currentRowChanged.connect(self._row_changed)
        self._refill()

    def _enable_rows(self, n):
        for i in range(4):
            for w in (self.labels[i], self.layers[i], self.colors[i], self.rowlabels[i]):
                w.setEnabled(i < n)

    def _refill(self, select=0):
        self._loading = True
        self.list.clear()
        self.list.addItems([p.name for p in self.entries])
        self._loading = False
        self._row = -1
        self.list.setCurrentRow(min(select, len(self.entries) - 1))

    def _row_changed(self, row):
        if self._loading:
            return
        if not self._commit():
            self._loading = True; self.list.setCurrentRow(self._row); self._loading = False
            return
        self._row = row
        if 0 <= row < len(self.entries):
            p = self.entries[row]
            self.name.setText(p.name); self.count.setValue(len(p.layers)); self.spacing.setValue(p.spacing)
            for i in range(4):
                has = i < len(p.layers)
                self.labels[i].setText(p.labels[i] if has else "")
                self.layers[i].setCurrentText(p.layers[i] if has else "")
                j = self.colors[i].findData(p.colors[i] if has else 7)
                self.colors[i].setCurrentIndex(max(0, j))
            self._enable_rows(len(p.layers))

    def _commit(self):
        r = self._row
        if not 0 <= r < len(self.entries):
            return True
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Color standards", "A standard needs a name."); return False
        if any(i != r and p.name == name for i, p in enumerate(self.entries)):
            QMessageBox.warning(self, "Color standards", f"There is already a standard named {name}."); return False
        n = self.count.value()
        labels = [self.labels[i].text().strip() for i in range(n)]
        layers = [self.layers[i].currentText().strip() for i in range(n)]
        if not all(labels) or not all(layers):
            QMessageBox.warning(self, "Color standards", "Every wire needs a label and a layer."); return False
        if len(set(layers)) != n:
            QMessageBox.warning(self, "Color standards", "Each wire needs its own layer."); return False
        colors = [int(self.colors[i].currentData()) for i in range(n)]
        self.entries[r] = m.MultilinePreset(name, layers, self.spacing.value(), colors, labels)
        item = self.list.item(r)
        if item is not None:
            item.setText(name)
        return True

    def on_autoname(self):
        name = self.name.text().strip()
        for i in range(self.count.value()):
            self.layers[i].setCurrentText(f"{name} {self.labels[i].text().strip()}".strip())

    def on_add(self):
        if not self._commit():
            return
        names = {p.name for p in self.entries}
        n = 1
        while f"Standard {n}" in names:
            n += 1
        nm = f"Standard {n}"
        self.entries.append(m.MultilinePreset(nm, [f"{nm} L1", f"{nm} L2"], 0.0, [7, 1], ["L1", "L2"]))
        self._refill(len(self.entries) - 1)

    def on_delete(self):
        r = self.list.currentRow()
        if r < 0 or len(self.entries) <= 1:
            return
        del self.entries[r]
        self._row = -1
        self._refill(max(0, r - 1))

    def accept(self):
        if self._commit():
            super().accept()

    def result_presets(self):
        return OrderedDict((p.name, p) for p in self.entries)
