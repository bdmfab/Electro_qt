"""Panel layout dialogs and the list of parts still to place."""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QDialogButtonBox, QComboBox, QDoubleSpinBox,
                               QRadioButton, QLineEdit, QLabel, QDockWidget, QListWidget, QListWidgetItem,
                               QPushButton, QWidget, QHBoxLayout)
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


class WireNumberDialog(QDialog):
    """Every wire number that ends at a dot, with how many dots it reaches: "01131 (8)". Double-click (or
    Apply) uses it for the selected terminal; right-click > Apply to multiple... asks how many terminals."""

    def __init__(self, parent, numbers, room=1, used=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidgetItem, QMenu
        used = used or {}
        self.setWindowTitle("Label from wire numbers")
        self.chosen = None                                   # (wire number, how many terminals)
        self._room = room
        self.list = QListWidget()
        for num, where in numbers.items():
            left = max(0, len(where) - used.get(num, 0))        # dots not yet given to a terminal
            it = QListWidgetItem(f"{num} x {left}" + ("" if left else "   (all used)"))
            it.setData(Qt.ItemDataRole.UserRole, (num, max(1, left)))
            if not left:
                it.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda _it: self._single())
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        info = QLabel("Wire numbers at the dots on the drawing; x N = dots not yet given to a terminal.\n"
                      "Select one and Apply, or right-click it: Apply to multiple...")
        if not numbers:
            info.setText("No wire numbers reach a dot yet (press Update wire numbers first).")
        apply = QPushButton("Apply to the selected terminal")
        apply.clicked.connect(self._single)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(apply); row.addWidget(cancel)
        lay = QVBoxLayout(self); lay.addWidget(info); lay.addWidget(self.list); lay.addLayout(row)
        self.resize(320, 420)

    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    def _single(self):
        cur = self._current()
        if cur is not None:
            self.chosen = (cur[0], 1)
            self.accept()

    def _menu(self, pos):
        from PySide6.QtWidgets import QMenu, QInputDialog
        it = self.list.itemAt(pos)
        if it is None:
            return
        self.list.setCurrentItem(it)
        num, n = it.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        a1 = menu.addAction("Apply to the selected terminal")
        a2 = menu.addAction(f"Apply to multiple...")
        act = menu.exec(self.list.mapToGlobal(pos))
        if act is a1:
            self._single()
        elif act is a2:
            k, ok = QInputDialog.getInt(self, "Apply to multiple", f"Number of terminals to label {num}:", n, 1, 500)
            if ok:
                self.chosen = (num, k)
                self.accept()


class TerminalLabelsDialog(QDialog):
    """Identifier, quantity and the label of every terminal of a block (stack)."""

    def __init__(self, parent, obj, project=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox, QTableWidget
        self.obj, self.project = obj, project
        self.setWindowTitle(f"Terminal labels - {obj.block}")
        self.ident = QLineEdit(obj.ident)
        self.first = QSpinBox(); self.first.setRange(0, 9999); self.first.setValue(obj.first)
        self.stack = obj.kind == "terminals"
        self.qty = QSpinBox(); self.qty.setRange(1, 500); self.qty.setValue(max(1, obj.qty))
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Label"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setRowCount(self.qty.value() if self.stack else 1)
        self._fill(0, pn.terminal_labels(obj))
        self.ident.textEdited.connect(lambda _t: self._auto())
        self.first.valueChanged.connect(lambda _v: self._auto())
        self.qty.valueChanged.connect(self._resize)
        note = QLabel("Editing the identifier or first number renumbers all terminals;\n"
                      "edit a label below to override just that one.")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form = QFormLayout(); form.addRow("Identifier", self.ident); form.addRow("First terminal number", self.first)
        if self.stack:
            form.addRow("Quantity", self.qty)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(note); lay.addWidget(self.table)
        if project is not None:
            wn = QPushButton("Label from wire numbers...")
            wn.setToolTip("Select a terminal below, then pick a wire number that ends at a dot")
            wn.clicked.connect(self._from_numbers)
            lay.addWidget(wn)
        lay.addWidget(bb)
        self.resize(380, 480)

    def count(self):
        return self.table.rowCount()

    def _fill(self, start, labels):
        from PySide6.QtWidgets import QTableWidgetItem
        for i, t in enumerate(labels):
            self.table.setItem(start + i, 0, QTableWidgetItem(t))

    def _auto_labels(self, n):
        tmp = m.PanelObj(self.obj.kind, 0, 0, 1, 1, qty=n, ident=self.ident.text().strip(), first=self.first.value())
        return pn.terminal_labels(tmp)

    def _auto(self):
        self._fill(0, self._auto_labels(self.count()))

    def _resize(self, n):
        if not self.stack:
            return
        old = self.count()
        keep = [self.table.item(i, 0).text() if self.table.item(i, 0) else "" for i in range(old)]
        self.table.setRowCount(n)
        if n > old:
            self._fill(old, self._auto_labels(n)[old:])         # new terminals continue the numbering
        else:
            self._fill(0, keep[:n])

    def _from_numbers(self):
        from PySide6.QtWidgets import QMessageBox
        from .. import dots
        row = max(0, self.table.currentRow())
        used = dict(dots.used_counts(self.project, self.obj))
        for i in range(self.count()):                       # labels already typed in this dialog
            it = self.table.item(i, 0)
            t = it.text().strip() if it else ""
            if t:
                used[t] = used.get(t, 0) + 1
        dlg = WireNumberDialog(self, dots.dot_numbers(self.project), self.count() - row, used)
        if not dlg.exec() or dlg.chosen is None:
            return
        number, k = dlg.chosen
        room = self.count() - row
        if k > room:
            if not self.stack:
                k = room
            else:
                B = QMessageBox.StandardButton
                r = QMessageBox.question(self, "Not enough terminals",
                                         f"{number} reaches {k} dots but only {room} terminal(s) are left from here.\n\n"
                                         f"Add the other {k - room} terminal(s) to the stack?",
                                         B.Yes | B.No | B.Cancel)
                if r == B.Cancel:
                    return
                if r == B.Yes:
                    self.qty.setValue(self.count() + k - room)       # grows the table
                else:
                    k = room
        for i in range(row, row + k):
            self.table.item(i, 0).setText(number)

    def values(self):
        """-> (ident, first, [labels], qty)"""
        return (self.ident.text().strip(), self.first.value(),
                [self.table.item(i, 0).text() for i in range(self.table.rowCount())],
                self.table.rowCount() if self.stack else self.obj.qty)


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
