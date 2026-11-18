"""Panel layout dialogs and the list of parts still to place."""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QDialogButtonBox, QComboBox, QDoubleSpinBox,
                               QRadioButton, QLineEdit, QLabel, QDockWidget, QListWidget, QListWidgetItem,
                               QPushButton, QWidget)
from .. import panel as pn
from .. import model as m


def _spin(val=0.0, lo=0.0, hi=100000.0):
    sp = QDoubleSpinBox(); sp.setDecimals(3); sp.setRange(lo, hi); sp.setValue(val)
    return sp


class _Units:
    """in / mm selector for a set of spin boxes (values are returned in inches)."""

    def __init__(self, spins):
        self.spins = spins
        self.combo = QComboBox(); self.combo.addItem("inches", 1.0); self.combo.addItem("mm", pn.MM)
        self.last = 1.0
        self.combo.currentIndexChanged.connect(self._changed)

    def _changed(self):
        k = self.combo.currentData()
        for sp in self.spins:
            sp.setValue(sp.value() * self.last / k)
        self.last = k

    def inches(self, sp):
        return sp.value() / self.combo.currentData()


class NewPanelDialog(QDialog):
    """Start a panel layout: type the back plate size, or take it from a block (an enclosure / sub-panel
    with a footprint)."""

    def __init__(self, parent, blocks):
        super().__init__(parent)
        self.setWindowTitle("New panel layout")
        self.title = QLineEdit("Panel layout")
        self.by_size = QRadioButton("Back plate size"); self.by_size.setChecked(True)
        self.w, self.h = _spin(24.0, 1), _spin(30.0, 1)
        self.units = _Units([self.w, self.h])
        self.by_block = QRadioButton("Take the size from a block")
        self.block = QComboBox()
        for b in blocks:
            if b.fp_w > 0 and b.fp_h > 0 and b.mount:
                self.block.addItem(f"{b.name}  ({b.fp_w:g} x {b.fp_h:g} in)", b.name)
        self.by_block.setEnabled(self.block.count() > 0)
        self.block.setEnabled(False)
        self.by_block.toggled.connect(self.block.setEnabled)
        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow(self.by_size)
        form.addRow("Units", self.units.combo)
        form.addRow("Width", self.w); form.addRow("Height", self.h)
        form.addRow(self.by_block); form.addRow("Block", self.block)
        if not self.block.count():
            form.addRow(QLabel("(Give a block a footprint in Part properties (Type On back plate) to list it here.)"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        """(title, width, height, block name or '') in inches."""
        if self.by_block.isChecked() and self.block.currentData():
            return self.title.text().strip() or "Panel layout", 0.0, 0.0, self.block.currentData()
        return self.title.text().strip() or "Panel layout", self.units.inches(self.w), self.units.inches(self.h), ""


class InsertRunDialog(QDialog):
    """Pick the DIN rail or wire duct to insert (it goes in 1 in long; drag the ends afterwards)."""

    def __init__(self, parent, kind):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("Insert DIN rail" if kind == "rail" else "Insert wire duct")
        self.combo = QComboBox()
        table = pn.RAILS if kind == "rail" else pn.DUCTS
        for name in table:
            self.combo.addItem(name, name)
        self.combo.addItem("Custom", "")
        self.a = _spin(1.378 if kind == "rail" else 1.5, 0.01)       # across: rail width / duct width
        self.b = _spin(0.295 if kind == "rail" else 3.0, 0.0)        # rail height / duct depth
        self.units = _Units([self.a, self.b])
        self.combo.currentIndexChanged.connect(self._preset)
        form = QFormLayout()
        form.addRow("Size", self.combo)
        form.addRow("Units", self.units.combo)
        form.addRow("Width (across)", self.a)
        form.addRow("Rail height" if kind == "rail" else "Duct depth", self.b)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self._preset()

    def _preset(self):
        key = self.combo.currentData()
        table = pn.RAILS if self.kind == "rail" else pn.DUCTS
        if key in table:
            k = self.units.combo.currentData()
            self.a.setValue(table[key][0] * k); self.b.setValue(table[key][1] * k)

    def spec(self):
        return {"kind": self.kind, "w": 1.0, "h": self.units.inches(self.a), "depth": self.units.inches(self.b)}


class TerminalsDialog(QDialog):
    """Add terminal blocks to the layout: which block, and how many (they stack side by side)."""

    def __init__(self, parent, blocks, next_ident=None):
        """blocks: the blocks of Library/Terminals. next_ident(prefix) -> the next free identifier (TB3 ...)."""
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox
        self.setWindowTitle("Add terminal blocks")
        self._next = next_ident or (lambda prefix: prefix + "1")
        self._prefix = {b.name: (b.tag_prefix or "TB") for b in blocks}
        self.ident = QLineEdit("")
        self.first = QSpinBox(); self.first.setRange(0, 9999); self.first.setValue(1)
        self.block = QComboBox()
        for b in blocks:
            if b.fp_w > 0 and b.fp_h > 0 and b.mount:
                self.block.addItem(f"{b.name}  ({b.fp_w:g} x {b.fp_h:g} in)", b.name)
        self.qty = QSpinBox(); self.qty.setRange(1, 500); self.qty.setValue(1)
        self.block.currentIndexChanged.connect(self._new_ident)
        self._new_ident()
        form = QFormLayout()
        form.addRow("Block (Library/Terminals)", self.block); form.addRow("Quantity", self.qty)
        form.addRow("Identifier", self.ident); form.addRow("First terminal number", self.first)
        form.addRow(QLabel("The identifier starts from the block's Tag prefix and counts up (TB1, TB2 ...).\n"
                           "Terminals are labelled identifier.number: TB1.1, TB1.2 ..."))
        if not self.block.count():
            form.addRow(QLabel("No block in the library folder Terminals has a footprint yet.\n"
                               "Put terminal blocks in a library folder named Terminals, then open its Part properties: "
                               "Type On back plate and set its size."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.block.count() > 0)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def _new_ident(self, *_):
        name = self.block.currentData()
        if name:
            self.ident.setText(self._next(self._prefix.get(name, "TB")))

    def values(self):
        return self.block.currentData(), self.qty.value(), self.ident.text().strip(), self.first.value()


class TerminalLabelsDialog(QDialog):
    """Identifier and the label of every terminal of a block (stack)."""

    def __init__(self, parent, obj):
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox, QTableWidget, QTableWidgetItem
        self.obj = obj
        self.setWindowTitle(f"Terminal labels - {obj.block}")
        self.ident = QLineEdit(obj.ident)
        self.first = QSpinBox(); self.first.setRange(0, 9999); self.first.setValue(obj.first)
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Label"])
        self.table.horizontalHeader().setStretchLastSection(True)
        n = max(1, obj.qty) if obj.kind == "terminals" else 1
        self.table.setRowCount(n)
        self._fill(pn.terminal_labels(obj))
        self.ident.textEdited.connect(lambda _t: self._auto())
        self.first.valueChanged.connect(lambda _v: self._auto())
        note = QLabel("Editing the identifier or first number renumbers all terminals;\nedit a label below to override just that one.")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form = QFormLayout(); form.addRow("Identifier", self.ident); form.addRow("First terminal number", self.first)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(note); lay.addWidget(self.table); lay.addWidget(bb)
        self.resize(360, 420)

    def _fill(self, labels):
        from PySide6.QtWidgets import QTableWidgetItem
        for i, t in enumerate(labels):
            self.table.setItem(i, 0, QTableWidgetItem(t))

    def _auto(self):
        tmp = m.PanelObj(self.obj.kind, 0, 0, 1, 1, qty=self.obj.qty, ident=self.ident.text().strip(), first=self.first.value())
        self._fill(pn.terminal_labels(tmp))

    def values(self):
        """-> (ident, first, [labels])"""
        return (self.ident.text().strip(), self.first.value(),
                [self.table.item(i, 0).text() for i in range(self.table.rowCount())])


class PanelSizeDialog(QDialog):
    """Type the exact size of a rail / duct / plate."""

    def __init__(self, parent, obj):
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox, QCheckBox
        self.setWindowTitle(f"Size - {pn.KIND_NAMES[obj.kind]}")
        self.obj = obj
        self.l, self.wd, self.dp = _spin(obj.w, 0.05), _spin(obj.h, 0.01), _spin(obj.depth, 0.0)
        self.qty = QSpinBox(); self.qty.setRange(1, 500); self.qty.setValue(max(1, obj.qty))
        self.xbom = QCheckBox("Exclude from BOM"); self.xbom.setChecked(obj.xbom)
        self.units = _Units([self.l, self.wd, self.dp])
        form = QFormLayout()
        form.addRow("Units", self.units.combo)
        if obj.kind == "terminals":
            form.addRow("Quantity", self.qty)
            self.l.setEnabled(False)                       # the length follows the quantity
        form.addRow("Length" if obj.kind in ("rail", "duct") else "Width", self.l)
        form.addRow("Width (across)" if obj.kind in ("rail", "duct") else "Height", self.wd)
        if obj.kind != "plate":
            form.addRow("Depth", self.dp)
        if obj.kind in ("part", "terminals") and not obj.tag:
            form.addRow(self.xbom)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        o = self.obj
        v = {"w": self.units.inches(self.l), "h": self.units.inches(self.wd), "depth": self.units.inches(self.dp),
             "qty": o.qty, "xbom": self.xbom.isChecked() if o.kind in ("part", "terminals") and not o.tag else o.xbom}
        if o.kind == "terminals":
            one = o.w / max(1, o.qty)                      # one block's width stays; the stack grows / shrinks
            v["qty"] = self.qty.value()
            v["w"] = one * v["qty"]
        return v


class PartsPanel(QDockWidget):
    """The schematic's parts that are not on a panel layout yet. Double-click one to place it."""
    place = Signal(str, str)               # tag, block name

    def __init__(self, parent=None):
        super().__init__("Panel parts", parent)
        self.setObjectName("panelparts")
        w = QWidget(); lay = QVBoxLayout(w)
        self.info = QLabel("")
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._go)
        self.btn = QPushButton("Place selected")
        self.btn.clicked.connect(self._go)
        lay.addWidget(self.info); lay.addWidget(self.list); lay.addWidget(self.btn)
        self.setWidget(w)
        self.setMinimumWidth(200)

    def refresh(self, project):
        needed, left = pn.needed_parts(project), pn.unplaced_parts(project)
        self.info.setText(f"{len(needed) - len(left)} of {len(needed)} parts placed")
        self.list.clear()
        from .. import profiles
        profs = profiles.load()
        for tag, block in left:
            blk = pn.effective_block(project, project.blocks.get(block), tag, profs)
            ok = pn.footprint_part(blk, tag) is not None
            it = QListWidgetItem(f"{tag}   {block}" + ("" if ok else "   (no footprint)"))
            it.setData(Qt.ItemDataRole.UserRole, (tag, block))
            if not ok:
                it.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(it)

    def _go(self, *_):
        it = self.list.currentItem()
        if it is not None:
            self.place.emit(*it.data(Qt.ItemDataRole.UserRole))
