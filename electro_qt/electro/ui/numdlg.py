"""Wire number dialog: auto / override / locked / ignore."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout, QComboBox, QLineEdit, QDialogButtonBox, QLabel


class WireNumberDialog(QDialog):
    def __init__(self, parent, mode="auto", value=""):
        super().__init__(parent)
        self.setWindowTitle("Wire number")
        self.mode = QComboBox()
        for text, v in (("Automatic (set by Update wire numbers)", "auto"),
                        ("Override (my number; the sequence goes on)", "override"),
                        ("Locked (never changed)", "locked"),
                        ("Ignore (never numbered automatically; type a number if you want one)", "ignore"),
                        ("Clear (no number at all)", "clear")):
            self.mode.addItem(text, v)
        if mode == "ignore" and not value:
            mode = "clear"
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        self.value = QLineEdit(value)
        self.mode.currentIndexChanged.connect(self._sync)
        form = QFormLayout()
        form.addRow("Mode", self.mode); form.addRow("Number", self.value)
        form.addRow(QLabel("Applies to the whole wire (every connected segment)."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self._sync()

    def _sync(self):
        self.value.setEnabled(self.mode.currentData() not in ("auto", "clear"))

    def values(self):
        mode = self.mode.currentData()
        if mode == "clear":
            return "ignore", ""                      # blank number, never numbered automatically
        return mode, ("" if mode == "auto" else self.value.text().strip())
