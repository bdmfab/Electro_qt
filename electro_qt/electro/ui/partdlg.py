"""Tag picker used by Part properties (partprops.py)."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QWidget, QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox,
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
