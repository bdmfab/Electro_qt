"""Wire number dialog: auto / override / locked / clear / goto."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout, QComboBox, QLineEdit, QDialogButtonBox, QLabel


class WireNumberDialog(QDialog):
    def __init__(self, parent, mode="auto", value="", others=()):
        """others = [(label, line_id)]: the numbered wires a goto can be tied to."""
        super().__init__(parent)
        self.setWindowTitle("Wire number")
        self.mode = QComboBox()
        for text, v in (("Automatic (set by Update wire numbers)", "auto"),
                        ("Override (my number; the sequence goes on)", "override"),
                        ("Locked (never changed)", "locked"),
                        ("Clear (no number at all)", "clear"),
                        ("Goto (this wire is the To; pick the From wire. From / To connectors named NUMBER-1, -2 ...)", "goto")):
            if v == "goto" and not others:
                continue
            self.mode.addItem(text, v)
        if mode == "ignore":
            mode = "clear"
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        self.value = QLineEdit(value)
        self.other = QComboBox()
        for label, lid in others:
            self.other.addItem(label, lid)
        self.mode.currentIndexChanged.connect(self._sync)
        form = QFormLayout()
        form.addRow("Mode", self.mode); form.addRow("Number", self.value); form.addRow("From wire", self.other)
        form.addRow(QLabel("Applies to the whole wire (every connected segment)."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self._sync()

    def _sync(self):
        m = self.mode.currentData()
        self.value.setEnabled(m in ("override", "locked"))
        self.other.setEnabled(m == "goto")

    def values(self):
        """-> (mode, value, line id to tie to or None)"""
        mode = self.mode.currentData()
        if mode == "clear":
            return "ignore", "", None                # blank number, never numbered automatically
        if mode == "goto":
            return "goto", "", self.other.currentData()
        return mode, ("" if mode == "auto" else self.value.text().strip()), None
