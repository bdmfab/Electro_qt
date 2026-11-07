"""Letter rules: a very small table. A block's Letter rule names one of these;
in a layer scheme, the pattern is replaced by the true / false result."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                               QPushButton, QDialogButtonBox, QLabel, QHeaderView)
from .. import model as m


class RulesDialog(QDialog):
    def __init__(self, parent, rules):
        super().__init__(parent)
        self.setWindowTitle("Letter rules")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Rule name", "Pattern", "Result if true", "Result if false"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for r in rules:
            self._add(r.name, r.pattern, r.if_true, r.if_false)
        add, rem = QPushButton("Add rule"), QPushButton("Delete rule")
        add.clicked.connect(lambda: self._add("", "<L|T>", "", ""))
        rem.clicked.connect(self._remove)
        row = QHBoxLayout(); row.addWidget(add); row.addWidget(rem); row.addStretch()
        note = QLabel("A block's Letter rule is one of these names. Where a layer scheme contains the pattern, "
                      "it becomes the 'true' result if a block with that rule touches the wire, else 'false'.\n"
                      "Example: motor  <L|T>  T  L")
        note.setWordWrap(True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addWidget(note); lay.addWidget(self.table); lay.addLayout(row); lay.addWidget(bb)
        self.resize(520, 300)

    def _add(self, *vals):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate(vals):
            self.table.setItem(r, c, QTableWidgetItem(v))

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def rules(self):
        out = []
        for r in range(self.table.rowCount()):
            cell = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
            if cell(0) and cell(1):
                out.append(m.PrefixRule(cell(0), cell(1), cell(2), cell(3)))
        return out
