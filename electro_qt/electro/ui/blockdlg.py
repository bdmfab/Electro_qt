"""Block data dialog: used by Make block and by Library > Edit data."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QLineEdit, QSpinBox, QComboBox,
                               QCheckBox, QDialogButtonBox, QLabel)
from .. import blocks as bk


class BlockDialog(QDialog):
    def __init__(self, parent, block=None, poles=1, folders=(), folder="", rules=(), slot_names=None):
        """block=None: making a new block (asks for a name and label lines).
        block=BlockDef: editing its data (the name is fixed)."""
        super().__init__(parent)
        self.editing = block is not None
        self.setWindowTitle("Block data" if self.editing else "Make block")
        b = block
        self.name = QLineEdit(b.name if b else "")
        self.name.setEnabled(not self.editing)
        self.desc = QLineEdit(b.description if b else "")
        self.part = QLineEdit(b.part_number if b else "")
        self.mfr = QLineEdit(b.manufacturer if b else "")
        self.link = QLineEdit(b.hyperlink if b else "")
        self.prefix = QLineEdit(b.tag_prefix if b else "")
        self.prefix.setToolTip("Device tag = prefix + page + zone, e.g. K + 03 + 14 = K0314")
        self.folder = QComboBox()
        self.folder.addItem("(top level)", "")
        for f in folders:
            self.folder.addItem(f, f)
        cur = b.folder if b else folder
        self.folder.setCurrentIndex(max(0, self.folder.findData(cur)))
        self.poles = QSpinBox(); self.poles.setRange(1, 12); self.poles.setValue(b.poles if b else poles)
        self.inc = QComboBox(); self.inc.addItem("None", 0); self.inc.addItem("+1", 1)
        self.inc.setCurrentIndex(1 if (b and b.increment == 1) else 0)
        self.rule = QComboBox()
        self.rule.addItem("(none)", "")
        names = [r.name for r in rules]
        if b and b.prefix_rule and b.prefix_rule not in names:
            names.append(b.prefix_rule)
        for n in names:
            self.rule.addItem(n, n)
        self.rule.setCurrentIndex(max(0, self.rule.findData(b.prefix_rule if b else "")))
        self.rule.setToolTip("A letter rule defined under Sheet > Letter rules...")
        self.origin = None
        if slot_names is not None and not self.editing:
            self.origin = QComboBox()
            for i, n in enumerate(slot_names):
                self.origin.addItem(f"Slot {i + 1}" + (f" ({n})" if n else ""), f"slot:{i}")
            self.origin.addItem("Center of the selection", "center")
            self.origin.addItem("Pick a point on the drawing...", "pick")
            self.origin.setToolTip("The point that sits on the cursor when the block is placed")
        form = QFormLayout()
        for lab, w in (("Name", self.name), ("Description", self.desc), ("Part number", self.part),
                       ("Manufacturer", self.mfr), ("Hyperlink", self.link), ("Tag prefix", self.prefix),
                       ("Folder", self.folder), ("Poles", self.poles), ("Wire number increment", self.inc),
                       ("Letter rule", self.rule)):
            form.addRow(lab, w)
        if self.origin is not None:
            form.addRow("Origin point", self.origin)
        self.labels = {}
        have = bk.label_lines_of(b) if b else ("description", "part_label", "tag")
        form.addRow(QLabel("Stacked label:"))
        self.pos = QComboBox(); self.pos.addItem("Above the part", "above"); self.pos.addItem("Right of the part", "right")
        self.pos.setCurrentIndex(0 if (not b or b.label_pos == "above") else 1)
        form.addRow("Position", self.pos)
        self.conn = QCheckBox("Off-page connector (parts with the same tag are one wire)")
        self.conn.setChecked(bool(b and b.connector))
        form.addRow(self.conn)
        for key, text in (("description", "Description"), ("part_label", "#Part number"), ("tag", "Tag"), ("xref", "Cross-reference")):
            cb = QCheckBox(text); cb.setChecked(key in have)
            self.labels[key] = cb
            form.addRow(cb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        v = {"name": self.name.text().strip(), "description": self.desc.text().strip(),
             "part_number": self.part.text().strip(), "manufacturer": self.mfr.text().strip(),
             "hyperlink": self.link.text().strip(), "tag_prefix": self.prefix.text().strip(),
             "folder": self.folder.currentData(), "poles": self.poles.value(), "increment": self.inc.currentData(),
             "prefix_rule": self.rule.currentData(), "connector": int(self.conn.isChecked())}
        v["labels"] = tuple(k for k, cb in self.labels.items() if cb.isChecked())
        v["label_pos"] = self.pos.currentData()
        if self.origin is not None:
            v["origin"] = self.origin.currentData()
        return v


class CopyBlockDialog(QDialog):
    """Copy a block definition under a new name, into a chosen folder."""

    def __init__(self, parent, src_name, folders, folder=""):
        super().__init__(parent)
        self.setWindowTitle(f"Copy block - {src_name}")
        self.name = QLineEdit(f"{src_name} copy")
        self.folder = QComboBox()
        self.folder.addItem("(top level)", "")
        for f in folders:
            self.folder.addItem(f, f)
        self.folder.setCurrentIndex(max(0, self.folder.findData(folder)))
        form = QFormLayout()
        form.addRow("New name", self.name); form.addRow("Into folder", self.folder)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        return self.name.text().strip(), self.folder.currentData()
