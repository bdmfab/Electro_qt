"""Copy-block dialog (Make block / Edit data / Part properties are in partprops.py)."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QLineEdit, QSpinBox, QComboBox,
                               QCheckBox, QDialogButtonBox, QLabel, QDoubleSpinBox, QWidget)
from .. import blocks as bk


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
