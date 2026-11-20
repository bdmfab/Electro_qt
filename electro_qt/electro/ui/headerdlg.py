"""Header styles: how the text above / beside a part (description, part number, tag ...) looks."""
from __future__ import annotations
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QFormLayout,
                               QDoubleSpinBox, QComboBox, QLabel, QDialogButtonBox, QInputDialog, QMessageBox,
                               QFontComboBox, QCheckBox, QPlainTextEdit)
from .. import model as m
from .. import richtext
from .textdlg import RichTextDialog

HINT = ("Type the header as it should read, one line per field. Variables: {DESC} description, {PART} part "
        "number, {LOC} tag (location), {XREF} cross-reference. Select a variable and give it its own size, "
        "colour and font (12 pt = the normal 0.1 in text height). A line with no value for its variables drops out.")


class HeaderStylesDialog(QDialog):
    """Edit the project's header styles (a copy; the caller takes result_styles() on OK)."""

    def __init__(self, parent, styles, used=()):
        super().__init__(parent)
        self.setWindowTitle("Header styles")
        self.resize(560, 420)
        self.styles = {k: copy.deepcopy(v) for k, v in styles.items()}
        self.used = set(used)
        self.list = QListWidget()
        self.list.addItems(list(self.styles))
        self.list.currentTextChanged.connect(self._show)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setMaximumHeight(90)
        self.gap = QDoubleSpinBox(); self.gap.setDecimals(3); self.gap.setRange(-2.0, 2.0)
        self.gap.setSingleStep(0.01); self.gap.setSuffix(" in")
        self.gap.setToolTip("How far the text sits from the part (above: from the top of the part; right: from its "
                            "right side; inside: from the corner). 0.1 in is the standard; a negative value pulls the text onto the part.")
        self.align = QComboBox()
        for lab, key in (("Automatic (suits the label position)", "auto"), ("Left", "left"), ("Centre", "center"),
                         ("Right", "right")):
            self.align.addItem(lab, key)
        self.spacing = QDoubleSpinBox(); self.spacing.setDecimals(2); self.spacing.setRange(0.5, 3.0)
        self.spacing.setSingleStep(0.05)
        self.edit_btn = QPushButton("Edit text, sizes and colours...")
        self.edit_btn.clicked.connect(self._edit)
        add, ren, dup, rem = (QPushButton(t) for t in ("New", "Rename", "Copy", "Delete"))
        add.clicked.connect(self._new); ren.clicked.connect(self._rename)
        dup.clicked.connect(self._copy); rem.clicked.connect(self._delete)
        side = QVBoxLayout()
        for b in (add, ren, dup, rem):
            side.addWidget(b)
        side.addStretch(1)
        form = QFormLayout()
        form.addRow("Header", self.preview)
        form.addRow("", self.edit_btn)
        form.addRow("Distance from part", self.gap)
        form.addRow("Justify", self.align)
        form.addRow("Line spacing", self.spacing)
        top = QHBoxLayout()
        top.addWidget(self.list, 1); top.addLayout(side); top.addLayout(form, 3)
        note = QLabel(HINT); note.setWordWrap(True); note.setStyleSheet("color:gray")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(top); lay.addWidget(note); lay.addWidget(bb)
        self._cur = None
        self.list.setCurrentRow(0)

    # ---- the selected style <-> the fields
    def _store(self):
        s = self.styles.get(self._cur)
        if s is None:
            return
        s.gap = self.gap.value()
        s.align = self.align.currentData()
        s.spacing = self.spacing.value()

    def _show(self, name):
        self._store()
        self._cur = name if name in self.styles else None
        s = self.styles.get(self._cur)
        for w in (self.gap, self.align, self.spacing, self.edit_btn):
            w.setEnabled(s is not None)
        if s is None:
            self.preview.setPlainText("")
            return
        self.preview.setPlainText(richtext.plain(s.template))
        self.gap.setValue(s.gap)
        self.align.setCurrentIndex(max(0, self.align.findData(s.align)))
        self.spacing.setValue(s.spacing)

    def _edit(self):
        s = self.styles.get(self._cur)
        if s is None:
            return
        dlg = RichTextDialog(self, s.template, True, f"Header style - {s.name}", "left", hint=HINT)
        if dlg.exec():
            s.template = dlg.result_markup()[0]
            self.preview.setPlainText(richtext.plain(s.template))

    # ---- the list
    def _ask(self, title, text=""):
        name, ok = QInputDialog.getText(self, title, "Name:", text=text)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self.styles and name != text:
            QMessageBox.information(self, title, "A header style with that name exists.")
            return None
        return name

    def _new(self):
        name = self._ask("New header style")
        if name:
            self._store()
            self.styles[name] = m.HeaderStyle(name)
            self.list.addItem(name); self.list.setCurrentRow(self.list.count() - 1)

    def _copy(self):
        src = self.styles.get(self._cur)
        name = self._ask("Copy header style", (self._cur or "") + " copy") if src else None
        if name:
            self._store()
            c = copy.deepcopy(self.styles[self._cur]); c.name = name
            self.styles[name] = c
            self.list.addItem(name); self.list.setCurrentRow(self.list.count() - 1)

    def _rename(self):
        old = self._cur
        if old is None:
            return
        name = self._ask("Rename header style", old)
        if name and name != old:
            self._store()
            s = self.styles.pop(old); s.name = name
            self.styles[name] = s
            if old in self.used:
                self.used.discard(old); self.used.add(name)
            self.renames = getattr(self, "renames", {}); self.renames[old] = name
            self._cur = None
            self.list.clear(); self.list.addItems(list(self.styles))
            self.list.setCurrentRow(list(self.styles).index(name))

    def _delete(self):
        name = self._cur
        if name is None or len(self.styles) <= 1:
            if name is not None:
                QMessageBox.information(self, "Header styles", "Keep at least one header style.")
            return
        if name in self.used and QMessageBox.question(
                self, "Delete", f"Parts use '{name}'. They will use the first remaining style. Delete it?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._store()
        del self.styles[name]
        self._cur = None
        self.list.clear(); self.list.addItems(list(self.styles)); self.list.setCurrentRow(0)

    def _ok(self):
        self._store()
        self.accept()

    def result_styles(self):
        return self.styles

    def result_renames(self):
        return getattr(self, "renames", {})
