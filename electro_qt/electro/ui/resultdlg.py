"""Export verification: what was written, where, and anything to watch out for."""
from __future__ import annotations
import os
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton, QStyle)


class ExportResultDialog(QDialog):
    def __init__(self, parent, title, files, summary="", warnings=()):
        """files = [path]; summary = one line (counts); warnings = [text] shown in an orange box."""
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        head = QLabel(f"<b>{summary or f'{len(files)} file(s) written'}</b>")
        head.setWordWrap(True)
        lay.addWidget(head)
        folder = os.path.dirname(files[0]) if files else ""
        if folder:
            where = QLabel(f"Folder: {folder}")
            where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            where.setWordWrap(True)
            lay.addWidget(where)
        box = QListWidget()
        for f in files:
            try:
                kb = os.path.getsize(f) / 1024
                box.addItem(f"{os.path.basename(f)}    ({kb:,.0f} KB)")
            except OSError:
                box.addItem(f"{os.path.basename(f)}    (NOT FOUND)")
        lay.addWidget(box, 1)
        if warnings:
            w = QLabel("<b>Check:</b><br>" + "<br>".join(w.replace("<", "&lt;") for w in warnings))
            w.setWordWrap(True)
            w.setStyleSheet("background:#fff1d6; color:#5a3b00; border:1px solid #e0a030; padding:6px;")
            lay.addWidget(w)
        row = QHBoxLayout()
        op = QPushButton("Open folder")
        op.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
        op.setEnabled(bool(folder))
        ok = QPushButton("OK"); ok.setDefault(True); ok.clicked.connect(self.accept)
        row.addWidget(op); row.addStretch(); row.addWidget(ok)
        lay.addLayout(row)
        self.resize(520, 120 + 24 * min(max(len(files), 3), 14) + (90 if warnings else 0))
