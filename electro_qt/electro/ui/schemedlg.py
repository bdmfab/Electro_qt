"""Build a wire-number scheme from a list of predefined parts."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
                               QDialogButtonBox, QLabel, QLineEdit, QMessageBox)

BASE_PARTS = [
    ("<page>", "Sheet page number, two digits"),
    ("<zone>", "Zone of the wire's left end, two digits"),
    ("<col>", "Column (1 = zones 00-24, 2 = 25-49)"),
    ("<incident>", "Start digit from the marked wire + increment blocks passed"),
    ("<phase_incident>", "One number per set of parallel phase wires (L1 L2 L3), counted along the circuit"),
    ("<g_incident>", "Global count 1, 2, 3 ... left to right, top to bottom (no mark needed)"),
    ("<phase>", "The layer's phase digit (L1 -> 1)"),
]
EXAMPLE = {"<page>": "03", "<zone>": "12", "<col>": "1", "<incident>": "2", "<g_incident>": "7", "<phase_incident>": "2", "<phase>": "1"}


class SchemeDialog(QDialog):
    def __init__(self, parent, rules, taken_names=()):
        super().__init__(parent)
        self.setWindowTitle("New wire-number scheme")
        self.taken = set(taken_names)
        parts = list(BASE_PARTS)
        seen = set()
        for r in rules:
            if r.pattern not in seen:
                seen.add(r.pattern)
                parts.append((r.pattern, f"Letter rule: {r.if_true or '-'} if a '{r.name}' block touches, else {r.if_false or '-'}"))
                EXAMPLE.setdefault(r.pattern, r.if_false)
        self.name = QLineEdit()
        self.avail = QListWidget()
        for tok, tip in parts:
            it = QListWidgetItem(f"{tok}   {tip}"); it.setData(Qt.ItemDataRole.UserRole, tok)
            self.avail.addItem(it)
        self.avail.itemDoubleClicked.connect(lambda _it: self.add_part())
        self.chosen = QListWidget()
        self.text = QLineEdit(); self.text.setPlaceholderText("fixed text, e.g. -")
        add, addt = QPushButton("Add part >"), QPushButton("Add text >")
        rem, up, dn = QPushButton("Remove"), QPushButton("Up"), QPushButton("Down")
        add.clicked.connect(self.add_part); addt.clicked.connect(self.add_text)
        rem.clicked.connect(self.remove); up.clicked.connect(lambda: self.move(-1)); dn.clicked.connect(lambda: self.move(1))
        self.preview = QLabel()
        left = QVBoxLayout(); left.addWidget(QLabel("Available parts")); left.addWidget(self.avail); left.addWidget(add)
        t = QHBoxLayout(); t.addWidget(self.text); t.addWidget(addt); left.addLayout(t)
        right = QVBoxLayout(); right.addWidget(QLabel("Scheme (in order)")); right.addWidget(self.chosen)
        b = QHBoxLayout(); [b.addWidget(w) for w in (rem, up, dn)]; right.addLayout(b)
        cols = QHBoxLayout(); cols.addLayout(left, 3); cols.addLayout(right, 2)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        nm = QHBoxLayout(); nm.addWidget(QLabel("Scheme name")); nm.addWidget(self.name); root.addLayout(nm)
        root.addLayout(cols); root.addWidget(self.preview); root.addWidget(bb)
        self.resize(720, 400)
        self._update()

    def add_part(self):
        it = self.avail.currentItem()
        if it is not None:
            self.chosen.addItem(it.data(Qt.ItemDataRole.UserRole)); self._update()

    def add_text(self):
        t = self.text.text()
        if t:
            self.chosen.addItem(t); self.text.clear(); self._update()

    def remove(self):
        r = self.chosen.currentRow()
        if r >= 0:
            self.chosen.takeItem(r); self._update()

    def move(self, d):
        r = self.chosen.currentRow(); n = r + d
        if r >= 0 and 0 <= n < self.chosen.count():
            it = self.chosen.takeItem(r); self.chosen.insertItem(n, it); self.chosen.setCurrentRow(n); self._update()

    def pattern(self):
        return "".join(self.chosen.item(i).text() for i in range(self.chosen.count()))

    def _update(self):
        pat = self.pattern(); ex = pat
        for k, v in EXAMPLE.items():
            ex = ex.replace(k, v)
        self.preview.setText(f"Pattern: {pat or '-'}      Example: {ex or '-'}")

    def _ok(self):
        n = self.name.text().strip()
        if not n or not self.pattern():
            QMessageBox.warning(self, "Scheme", "Give the scheme a name and at least one part."); return
        if n in self.taken:
            QMessageBox.warning(self, "Scheme", f"There is already a scheme named {n}."); return
        self.accept()

    def result_scheme(self):
        return self.name.text().strip(), self.pattern()
