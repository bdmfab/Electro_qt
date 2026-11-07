"""Layer editor. Layers are user-made; 'Wire layer' is a property, and the
numbering options appear once it is ticked."""
from __future__ import annotations
import dataclasses
from collections import OrderedDict
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget,
                               QPushButton, QLineEdit, QComboBox, QCheckBox, QGroupBox,
                               QDialogButtonBox, QMessageBox, QLabel)
from .. import model as m
from .schemedlg import SchemeDialog
from .items import aci_color, PALETTE, LINEWEIGHTS
LINETYPES = ["continuous", "dashed", "dotted"]
PRESETS = [("AC   <incident><L|T><phase>", "<incident><L|T><phase>"),
           ("AC sets   <phase_incident><L|T><phase>", "<phase_incident><L|T><phase>"),
           ("DC   <page><zone><incident>", "<page><zone><incident>"),
           ("Global   <g_incident>", "<g_incident>")]


def _swatch(color):
    pm = QPixmap(14, 14); pm.fill(aci_color(color)); return QIcon(pm)


class LayerDialog(QDialog):
    def __init__(self, parent, layers, used_names, rules=(), schemes=None):
        super().__init__(parent)
        self.setWindowTitle("Layers")
        self.rules = list(rules)
        self.schemes = dict(schemes or {})
        self.extra = ""                      # pattern of a layer that matches no named scheme
        self.resize(640, 380)
        self.used = set(used_names)
        self.entries = [[name, dataclasses.replace(l)] for name, l in layers.items()]
        self._row = -1
        self._loading = False

        self.list = QListWidget()
        add, rem = QPushButton("Add"), QPushButton("Delete")
        add.clicked.connect(self.on_add); rem.clicked.connect(self.on_delete)
        left = QVBoxLayout(); left.addWidget(self.list)
        bl = QHBoxLayout(); bl.addWidget(add); bl.addWidget(rem); left.addLayout(bl)

        self.name = QLineEdit()
        self.color = QComboBox()
        for n, (label, _) in PALETTE.items():
            self.color.addItem(_swatch(n), label, n)
        self.linetype = QComboBox(); self.linetype.addItems(LINETYPES)
        self.weight = QComboBox()
        for w in LINEWEIGHTS:
            self.weight.addItem("Default" if w == 0 else f"{w:.2f} mm", w)
        self.wire = QCheckBox("Wire layer")
        self.numbered = QCheckBox("Number the wires on this layer")
        self.preset = QComboBox()
        self.pattern = QLineEdit(); self.pattern.setReadOnly(True)
        self._prev = 0
        grp = QGroupBox("Wire numbering")
        gf = QFormLayout(grp)
        gf.addRow(self.numbered)
        gf.addRow("Scheme", self.preset)
        gf.addRow("Pattern", self.pattern)
        gf.addRow(QLabel("Numbers are assigned later by the numbering update."))
        self.group = grp

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Color", self.color)
        form.addRow("Linetype", self.linetype)
        form.addRow("Line weight", self.weight)
        form.addRow(self.wire)
        right = QVBoxLayout(); right.addLayout(form); right.addWidget(grp); right.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        top = QHBoxLayout(); top.addLayout(left, 1); top.addLayout(right, 2)
        root = QVBoxLayout(self); root.addLayout(top); root.addWidget(bb)

        self.wire.toggled.connect(self.group.setEnabled)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.list.currentRowChanged.connect(self._row_changed)
        self._refill()
        self.list.setCurrentRow(0)

    # --------------------------------------------------------------- list
    def _label(self, entry):
        return entry[1].name + ("   (wire)" if entry[1].kind == "wire" else "")

    def _refill(self, select=0):
        self._loading = True
        self.list.clear()
        for ent in self.entries:
            self.list.addItem(self._label(ent))
            self.list.item(self.list.count() - 1).setIcon(_swatch(ent[1].color))
        self._loading = False
        self._row = -1
        self.list.setCurrentRow(min(select, len(self.entries) - 1))

    def _row_changed(self, row):
        if self._loading:
            return
        if not self._commit():
            self._loading = True
            self.list.setCurrentRow(self._row)
            self._loading = False
            return
        self._row = row
        self._load(row)

    def _load(self, row):
        if not 0 <= row < len(self.entries):
            return
        lay = self.entries[row][1]
        self._loading = True
        self.name.setText(lay.name)
        self.name.setEnabled(lay.name != "0")
        i = self.color.findData(lay.color)
        if i < 0:
            self.color.addItem(_swatch(lay.color), f"ACI {lay.color}", lay.color)
            i = self.color.count() - 1
        self.color.setCurrentIndex(i)
        self.linetype.setCurrentText(lay.linetype if lay.linetype in LINETYPES else "continuous")
        wi = self.weight.findData(lay.lineweight)
        if wi < 0:
            self.weight.addItem(f"{lay.lineweight:.2f} mm", lay.lineweight); wi = self.weight.count() - 1
        self.weight.setCurrentIndex(wi)
        self.wire.setChecked(lay.kind == "wire")
        self.group.setEnabled(lay.kind == "wire")
        self.numbered.setChecked(lay.numbered)
        self.pattern.setText(lay.scheme)
        self._fill_schemes(lay.scheme)
        self._loading = False

    def _fill_schemes(self, current):
        """Combo = built-in schemes, this project's own, then 'New...'. The current pattern is
        selected (added as 'Custom' if it matches nothing)."""
        items = [(l, p) for l, p in PRESETS] + [(f"{k}   {v}", v) for k, v in self.schemes.items()]
        if current and all(p != current for _, p in items):
            items.append((f"Custom   {current}", current))
        self.preset.blockSignals(True)
        self.preset.clear()
        self.items = items
        for label, _ in items:
            self.preset.addItem(label)
        self.preset.addItem("New...")
        idx = next((k for k, (_, p) in enumerate(items) if p == current), 0)
        self.preset.setCurrentIndex(idx)
        self.preset.blockSignals(False)
        self._prev = idx

    def _preset_changed(self, idx):
        if self._loading:
            return
        if idx == len(self.items):                      # "New..."
            dlg = SchemeDialog(self, self.rules, {k for k in self.schemes} | {l.split()[0] for l, _ in PRESETS})
            if dlg.exec():
                name, pat = dlg.result_scheme()
                self.schemes[name] = pat
                self.pattern.setText(pat)
                self._fill_schemes(pat)
            else:
                self.preset.blockSignals(True); self.preset.setCurrentIndex(self._prev); self.preset.blockSignals(False)
            return
        self._prev = idx
        self.pattern.setText(self.items[idx][1])

    def _commit(self) -> bool:
        """Write the form back into the current entry. False if the name is invalid."""
        r = self._row
        if not 0 <= r < len(self.entries):
            return True
        lay = self.entries[r][1]
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Layers", "A layer needs a name."); return False
        if any(i != r and e[1].name == name for i, e in enumerate(self.entries)):
            QMessageBox.warning(self, "Layers", f"There is already a layer named {name}."); return False
        lay.name = name
        lay.color = int(self.color.currentData())
        lay.linetype = self.linetype.currentText()
        lay.lineweight = float(self.weight.currentData())
        wire = self.wire.isChecked()
        lay.kind = "wire" if wire else "graphics"
        lay.numbered = wire and self.numbered.isChecked()
        lay.scheme = self.pattern.text().strip() if wire else ""
        item = self.list.item(r)
        if item is not None:
            item.setText(self._label(self.entries[r])); item.setIcon(_swatch(lay.color))
        return True

    # ------------------------------------------------------------ actions
    def on_add(self):
        if not self._commit():
            return
        base, n = "LAYER", 1
        names = {e[1].name for e in self.entries}
        while f"{base}{n}" in names:
            n += 1
        self.entries.append([None, m.Layer(f"{base}{n}", 7, "graphics")])
        self._refill(len(self.entries) - 1)

    def on_delete(self):
        r = self.list.currentRow()
        if r < 0:
            return
        orig, lay = self.entries[r]
        if lay.name == "0" or orig == "0":
            QMessageBox.information(self, "Layers", "Layer 0 cannot be deleted."); return
        if orig is not None and orig in self.used:
            QMessageBox.information(self, "Layers", f"Layer {orig} has drawing objects on it; move or delete them first.")
            return
        del self.entries[r]
        self._row = -1
        self._refill(max(0, r - 1))

    def accept(self):
        if self._commit():
            super().accept()

    def result_schemes(self):
        return dict(self.schemes)

    def result_layers(self):
        """-> (OrderedDict name->Layer, {original_name: new_name} for renamed layers)"""
        layers = OrderedDict((e[1].name, e[1]) for e in self.entries)
        renames = {orig: lay.name for orig, lay in self.entries if orig is not None and orig != lay.name}
        return layers, renames
