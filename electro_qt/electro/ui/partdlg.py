"""Edit one placed part: description, part number, tag, label lines, terminal names."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox,
                               QDialogButtonBox, QTableWidget, QTableWidgetItem, QPushButton, QSpinBox,
                               QLabel, QHeaderView)
from .. import blocks as bk

LINES = (("description", "Description"), ("part_label", "#Part number"), ("tag", "Tag"), ("xref", "Cross-reference"))


class TagPickerDialog(QDialog):
    """Table of every placed block; pick one to copy its tag."""

    def __init__(self, parent, project, skip=None):
        super().__init__(parent)
        self.setWindowTitle("Pick a tag")
        rows = [r for r in bk.placed_blocks(project) if r["tag"] and r["ref"] is not skip]
        self.table = QTableWidget(len(rows), 5)
        self.table.setHorizontalHeaderLabels(["Tag", "Sheet", "Zone", "Block", "Description"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        for i, r in enumerate(rows):
            for j, v in enumerate((r["tag"], f"{r['page']:02d}", r["zone"], r["block"], r["description"])):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda *_: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addWidget(self.table); lay.addWidget(bb)
        self.resize(620, 360)
        self._rows = rows

    def chosen(self):
        r = self.table.currentRow()
        return self._rows[r] if 0 <= r < len(self._rows) else None


class PartDialog(QDialog):
    def __init__(self, parent, project, block, ref):
        super().__init__(parent)
        self.project, self.block, self.ref = project, block, ref
        self.setWindowTitle(f"Part properties - {ref.block}")
        p = ref.props
        self.desc = QLineEdit(p.get("description", block.description))
        self.part = QLineEdit(p.get("part_number", block.part_number))
        self.mfr = QLineEdit(p.get("manufacturer", block.manufacturer))
        self.tag = QLineEdit(ref.tag)
        self.link = ref.props.get("tag_link") if ref.props.get("tag_mode") == "linked" else None
        self.tag.textEdited.connect(lambda _t: setattr(self, "link", None))      # typing breaks the link
        pick = QPushButton("Pick...")
        pick.setToolTip("Take the tag of another placed block (e.g. the coil). The tag then follows that "
                        "block when tags are updated.")
        pick.clicked.connect(self._pick)
        trow = QHBoxLayout(); trow.addWidget(self.tag); trow.addWidget(pick)
        form = QFormLayout()
        form.addRow("Description", self.desc); form.addRow("Part number", self.part)
        form.addRow("Manufacturer", self.mfr); form.addRow("Tag", trow)
        hidden = set(p.get("hide", "").split(","))
        self.show = {}
        form.addRow(QLabel("Label lines shown:"))
        for key, text in LINES:
            cb = QCheckBox(text); cb.setChecked(key not in hidden)
            self.show[key] = cb; form.addRow(cb)
        self.table = QTableWidget(len(block.slots), 2)
        self.table.setHorizontalHeaderLabels(["Slot", "Terminal"])
        for i, s in enumerate(block.slots):
            it = QTableWidgetItem(f"{i + 1}  ({s.x:+.2f}, {s.y:+.2f})")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(bk.slot_name(ref, i, s)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(170)
        pair = QPushButton("Pair numbering...")
        pair.setToolTip("Fill the terminals as pairs (13/14, 23/24 ...). You can still edit any of them.")
        pair.clicked.connect(self._pairs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form)
        if block.slots:
            lay.addWidget(QLabel("Terminals:")); lay.addWidget(self.table); lay.addWidget(pair)
        lay.addWidget(bb)

    def _pick(self):
        dlg = TagPickerDialog(self, self.project, skip=self.ref)
        if dlg.exec() and dlg.chosen() is not None:
            row = dlg.chosen()
            self.tag.setText(row["tag"])
            self.link = row["ref"].id

    def _pairs(self):
        d = QDialog(self); d.setWindowTitle("Pair numbering")
        first, step = QSpinBox(), QSpinBox()
        first.setRange(0, 9999); first.setValue(13)
        step.setRange(1, 999); step.setValue(10)
        f = QFormLayout(); f.addRow("First number", first); f.addRow("Step between pairs", step)
        f.addRow(QLabel("13 / 10 gives 13,14  23,24 ...   1 / 2 gives 1,2  3,4 ..."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        lay = QVBoxLayout(d); lay.addLayout(f); lay.addWidget(bb)
        if d.exec():
            for i, n in enumerate(bk.pair_numbers(self.table.rowCount(), first.value(), step.value())):
                self.table.item(i, 1).setText(n)

    def result(self):
        """-> (tag, props) for the part."""
        b, old = self.block, self.ref.props
        keep = {k: v for k, v in old.items()
                if k not in ("description", "part_number", "manufacturer", "hide", "tag_mode", "tag_link")
                and not k.startswith("term")}
        for key, widget, default in (("description", self.desc, b.description),
                                     ("part_number", self.part, b.part_number),
                                     ("manufacturer", self.mfr, b.manufacturer)):
            if widget.text().strip() != default:
                keep[key] = widget.text().strip()
        hide = [k for k, cb in self.show.items() if not cb.isChecked()]
        if hide:
            keep["hide"] = ",".join(hide)
        for i, s in enumerate(b.slots):
            name = self.table.item(i, 1).text().strip()
            if name != s.terminal:
                keep[f"term{i}"] = name
        tag = self.tag.text().strip()
        mode = old.get("tag_mode")
        if self.link:
            mode, keep["tag_link"] = "linked", self.link
        elif tag != self.ref.tag or mode == "linked":
            mode = "manual"
        if mode:
            keep["tag_mode"] = mode
        return tag, keep
