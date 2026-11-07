"""Title block information: project-wide (job, drawn by, date) and per-sheet (name, 4 title lines)."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QLineEdit, QGroupBox, QDialogButtonBox)


class TitleBlockDialog(QDialog):
    def __init__(self, parent, info: dict, sheet):
        super().__init__(parent)
        self.setWindowTitle("Title block")
        self.job = QLineEdit(info.get("job", ""))
        self.drawn = QLineEdit(info.get("drawn", ""))
        self.date = QLineEdit(info.get("date", ""))
        self.name = QLineEdit(sheet.title)
        self.lines = [QLineEdit(t) for t in sheet.title_lines]
        g1 = QGroupBox("Whole project"); f1 = QFormLayout(g1)
        f1.addRow("Job", self.job); f1.addRow("Drawn by", self.drawn); f1.addRow("Date", self.date)
        g2 = QGroupBox(f"This sheet ({sheet.page:02d})"); f2 = QFormLayout(g2)
        f2.addRow("Tab name", self.name)
        for i, e in enumerate(self.lines, 1):
            f2.addRow(f"Title line {i}", e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addWidget(g1); lay.addWidget(g2); lay.addWidget(bb)
        self.resize(420, 380)

    def result_values(self):
        return ({"job": self.job.text().strip(), "drawn": self.drawn.text().strip(),
                 "date": self.date.text().strip()},
                self.name.text().strip(), [e.text().strip() for e in self.lines])
