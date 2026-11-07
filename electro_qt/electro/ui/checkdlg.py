"""Rule check results: a list that stays open while you fix things. Double-click goes to the spot."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
                               QLabel, QHeaderView, QAbstractItemView, QComboBox)
from .. import rules


class RuleCheckDialog(QDialog):
    def __init__(self, parent, run, goto, export):
        """run() -> [Issue]; goto(page, x, y); export(issues)."""
        super().__init__(parent)
        self.setWindowTitle("Rule check")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self._run, self._goto, self._export = run, goto, export
        self.issues = []
        self.summary = QLabel()
        self.filter = QComboBox()
        self.filter.addItem("All categories", "")
        for c in rules.CATEGORIES:
            self.filter.addItem(c, c)
        self.filter.currentIndexChanged.connect(self._fill)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(rules.HEADER)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._go)
        again, exp, close = QPushButton("Check again"), QPushButton("Export CSV..."), QPushButton("Close")
        again.clicked.connect(self.refresh)
        exp.clicked.connect(lambda: self._export(self._shown()))
        close.clicked.connect(self.close)
        top = QHBoxLayout(); top.addWidget(self.summary, 1); top.addWidget(self.filter)
        row = QHBoxLayout(); row.addWidget(again); row.addWidget(exp); row.addStretch(); row.addWidget(close)
        hint = QLabel("Double-click a line to go to it. Nothing is changed by the check.")
        hint.setStyleSheet("color:gray")
        lay = QVBoxLayout(self); lay.addLayout(top); lay.addWidget(self.table); lay.addWidget(hint); lay.addLayout(row)
        self.resize(820, 440)
        self.refresh()

    def refresh(self):
        self.issues = self._run()
        self._fill()

    def _shown(self):
        c = self.filter.currentData()
        return [i for i in self.issues if not c or i.category == c]

    def _fill(self, *_):
        shown = self._shown()
        self.table.setRowCount(len(shown))
        for r, i in enumerate(shown):
            for c, v in enumerate((i.category, f"{i.page:02d}", i.zone, i.message)):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.summary.setText("No problems found." if not self.issues else
                             f"{len(self.issues)} thing(s) to look at" +
                             (f" ({len(shown)} shown)" if len(shown) != len(self.issues) else ""))

    def _go(self, row, _col):
        shown = self._shown()
        if 0 <= row < len(shown):
            i = shown[row]
            self._goto(i.page, i.x, i.y)
