"""Properties panel: shows the selection's layer / colour / line weight (and text
font, height, justification) and applies changes as one undo step."""
from __future__ import annotations
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QDockWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QPushButton
from .. import model as m
from ..geometry import leaves
from .items import LINEWEIGHTS, PALETTE, aci_color
from .scene import KEEP

VARIES = "__varies__"


class PropertiesPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Properties", parent)
        self.setObjectName("properties")
        self.scene = None
        self._busy = False
        w = QWidget(); self.form = QFormLayout(w)
        self.info = QLabel("Nothing selected")
        self.layer = QComboBox(); self.color = QComboBox(); self.weight = QComboBox()
        self.tstyle = QComboBox()
        self.part_btn = QPushButton("Part properties...")
        self.part_btn.clicked.connect(self._part)
        self.tag = QLineEdit(); self.tag.setPlaceholderText("(blocks only)")
        self.radius = QDoubleSpinBox(); self.radius.setDecimals(3); self.radius.setRange(0.01, 999.0)
        self.radius.setSingleStep(0.05); self.radius.setSuffix(" in")
        for label, wd in (("", self.info), ("Layer", self.layer), ("Color", self.color),
                          ("Line weight", self.weight), ("Text style", self.tstyle),
                          ("Radius", self.radius), ("Device tag", self.tag), ("", self.part_btn)):
            self.form.addRow(label, wd) if label else self.form.addRow(wd)
        self.layer.activated.connect(self._layer)
        self.color.activated.connect(self._color)
        self.weight.activated.connect(self._weight)
        self.tstyle.activated.connect(self._tstyle)
        self.radius.editingFinished.connect(self._radius)
        self.tag.editingFinished.connect(self._tag)
        self.setWidget(w)
        self.setMinimumWidth(220)
        self.refresh()

    def attach(self, scene):
        if self.scene is not None:
            try:
                self.scene.selectionChanged.disconnect(self.refresh)
                self.scene.undo.indexChanged.disconnect(self.refresh)
            except (RuntimeError, TypeError):
                pass
        self.scene = scene
        if scene is not None:
            scene.selectionChanged.connect(self.refresh)
            scene.undo.indexChanged.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ show
    @staticmethod
    def _set(combo, items, value, varies):
        combo.clear()
        if varies:
            combo.addItem("-- varies --", VARIES)
        for icon, text, data in items:
            combo.addItem(icon, text, data) if icon else combo.addItem(text, data)
        combo.setCurrentIndex(0 if varies else max(0, combo.findData(value)))

    def refresh(self, *_):
        sc = self.scene
        sel = sc.selected_entities() if sc is not None else []
        ents = list(leaves(sel)) if sel else []
        self._busy = True
        try:
            enabled = bool(ents)
            for wd in (self.layer, self.color, self.weight):
                wd.setEnabled(enabled)
            texts = [e for e in ents if isinstance(e, m.Text)]
            circles = [e for e in ents if isinstance(e, m.Circle)]
            self.tstyle.setEnabled(bool(texts))
            self.radius.setEnabled(bool(circles))
            refs = [e for e in ents if isinstance(e, m.BlockRef)]
            self.tag.setEnabled(len(refs) == 1)
            self.part_btn.setEnabled(len(refs) == 1)
            self.tag.setText(refs[0].tag if len(refs) == 1 else "")
            self.info.setText(f"{len(sel)} object(s) selected" if sel else "Nothing selected")
            if not ents:
                for c in (self.layer, self.color, self.weight):
                    c.clear()
                return
            layers = []
            for name, lay in sc.project.layers.items():
                pm = QPixmap(14, 14); pm.fill(aci_color(lay.color))
                layers.append((QIcon(pm), name, name))
            ls = {e.style.layer for e in ents}
            self._set(self.layer, layers, next(iter(ls)), len(ls) > 1)
            cols = [(None, "By layer", None)]
            for n, (nm, _) in PALETTE.items():
                pm = QPixmap(14, 14); pm.fill(aci_color(n))
                cols.append((QIcon(pm), nm, n))
            cs = {e.style.color for e in ents}
            self._set(self.color, cols, next(iter(cs)), len(cs) > 1)
            ws = [(None, "By layer" if w == 0 else f"{w:g} mm", w) for w in LINEWEIGHTS]
            wset = {e.style.width for e in ents}
            self._set(self.weight, ws, next(iter(wset)), len(wset) > 1)
            if texts:
                names = [(None, n, n) for n in sc.project.text_styles]
                used = {e.tstyle for e in texts}
                self._set(self.tstyle, names, next(iter(used)), len(used) > 1)
            else:
                self.tstyle.clear()
            if circles:
                self.radius.setValue(circles[0].r)
        finally:
            self._busy = False

    # ------------------------------------------------------------ apply
    def _layer(self, _):
        d = self.layer.currentData()
        if not self._busy and d != VARIES and self.scene:
            self.scene.apply_props(layer=d)

    def _color(self, _):
        d = self.color.currentData()
        if not self._busy and d != VARIES and self.scene:
            self.scene.apply_props(color=d)

    def _weight(self, _):
        d = self.weight.currentData()
        if not self._busy and d != VARIES and self.scene:
            self.scene.apply_props(weight=d)

    def _tstyle(self, _):
        d = self.tstyle.currentData()
        if not self._busy and d != VARIES and self.scene:
            self.scene.apply_props(tstyle=d)

    def _part(self):
        refs = [e for e in self.scene.selected_entities() if isinstance(e, m.BlockRef)] if self.scene else []
        if len(refs) == 1:
            self.scene.edit_part(refs[0])

    def _tag(self):
        if self._busy or not self.scene or not self.tag.isEnabled():
            return
        refs = [e for e in self.scene.selected_entities() if isinstance(e, m.BlockRef)]
        if len(refs) == 1 and refs[0].tag != self.tag.text().strip():
            self.scene.set_tag(refs[0], self.tag.text().strip())

    def _radius(self):
        if not self._busy and self.scene and self.radius.isEnabled():
            cs = [e for e in self.scene.selected_entities() if isinstance(e, m.Circle)]
            if cs and abs(cs[0].r - self.radius.value()) > 1e-9:
                self.scene.apply_props(radius=self.radius.value())
