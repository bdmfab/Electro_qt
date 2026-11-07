"""Text properties: font, height, colour."""
from __future__ import annotations
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QFontComboBox, QDoubleSpinBox,
                               QComboBox, QDialogButtonBox)
from .items import PALETTE, aci_color


def fill_color_combo(combo: QComboBox, current=None):
    """'By layer' (None) followed by the palette."""
    combo.addItem("By layer", None)
    for n, (name, _) in PALETTE.items():
        pm = QPixmap(14, 14); pm.fill(aci_color(n))
        combo.addItem(QIcon(pm), name, n)
    i = combo.findData(current)
    combo.setCurrentIndex(max(0, i))


class TextPropsDialog(QDialog):
    def __init__(self, parent, font="", height=0.12, color=None):
        super().__init__(parent)
        self.setWindowTitle("Text properties")
        self.font_box = QFontComboBox()
        if font:
            self.font_box.setCurrentFont(QFont(font))
        self.height = QDoubleSpinBox()
        self.height.setDecimals(3); self.height.setRange(0.02, 5.0); self.height.setSingleStep(0.01)
        self.height.setValue(height); self.height.setSuffix(" in")
        self.color = QComboBox()
        fill_color_combo(self.color, color)
        form = QFormLayout()
        form.addRow("Font", self.font_box)
        form.addRow("Height", self.height)
        form.addRow("Color", self.color)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

    def values(self):
        return self.font_box.currentFont().family(), self.height.value(), self.color.currentData()


# ---------------------------------------------------------------------------------------- rich text
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor, QBrush, QColor
from PySide6.QtWidgets import QTextEdit, QToolButton, QHBoxLayout, QLabel
from .. import richtext

BASE_PT = 12.0
SIZES = [6, 8, 10, 12, 14, 18, 24, 36]
COLOR_PROP = 0x100001          # QTextFormat user property holding the palette index


def _fmt(run) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setFontWeight(700 if run.bold else 400)
    f.setFontItalic(run.italic)
    f.setFontUnderline(run.underline)
    f.setFontPointSize(BASE_PT * run.size)
    if run.color:
        f.setProperty(COLOR_PROP, int(run.color))
        f.setForeground(QBrush(aci_color(run.color)))
    return f


def markup_to_document(edit: QTextEdit, markup: str):
    edit.clear()
    cur = edit.textCursor()
    for i, runs in enumerate(richtext.parse(markup)):
        if i:
            cur.insertBlock()
        for r in runs:
            cur.insertText(r.text, _fmt(r))
    cur.setPosition(0)
    edit.setTextCursor(cur)


def document_to_lines(edit: QTextEdit):
    lines = []
    blk = edit.document().begin()
    while blk.isValid():
        runs = []
        it = blk.begin()
        while not it.atEnd():
            fr = it.fragment()
            if fr.isValid():
                f = fr.charFormat()
                col = f.property(COLOR_PROP)
                for k, part in enumerate(fr.text().replace(" ", "\n").split("\n")):
                    if k:
                        lines.append(runs); runs = []
                    if part:
                        runs.append(richtext.Run(
                            part, f.fontWeight() >= 600, f.fontItalic(), f.fontUnderline(),
                            round((f.fontPointSize() or BASE_PT) / BASE_PT, 3),
                            int(col) if isinstance(col, int) else None))
            it += 1
        lines.append(runs)
        blk = blk.next()
    return lines


class RichTextDialog(QDialog):
    """Multi-line text with bold / italic / underline, size and colour per selection."""

    def __init__(self, parent, markup="", rich=False, title="Text", align="left"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 320)
        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)
        self.edit.setFontPointSize(BASE_PT)
        markup_to_document(self.edit, markup)
        self.edit.setFontPointSize(BASE_PT)

        def tbtn(label, tip, slot, style=""):
            b = QToolButton(); b.setText(label); b.setToolTip(tip); b.setCheckable(True)
            b.setStyleSheet(style); b.clicked.connect(slot)
            return b
        self.b_bold = tbtn("B", "Bold (Ctrl+B)", self._bold, "font-weight:bold")
        self.b_it = tbtn("I", "Italic (Ctrl+I)", self._italic, "font-style:italic")
        self.b_ul = tbtn("U", "Underline (Ctrl+U)", self._underline, "text-decoration:underline")
        self.b_bold.setShortcut("Ctrl+B"); self.b_it.setShortcut("Ctrl+I"); self.b_ul.setShortcut("Ctrl+U")
        self.align = align if align in ("left", "center", "right") else "left"
        self.b_align = {}
        for key, lab, tip in (("left", "L", "Justify left: the text starts at its point"),
                              ("center", "C", "Justify center: the text is centered on its point"),
                              ("right", "R", "Justify right: the text ends at its point")):
            b = tbtn(lab, tip, lambda _=False, k=key: self._set_align(k))
            b.setChecked(key == self.align)
            self.b_align[key] = b
        self.size = QComboBox()
        for s in SIZES:
            self.size.addItem(f"{s} pt", s / BASE_PT)
        self.size.setCurrentIndex(SIZES.index(12))
        self.size.activated.connect(self._size)
        self.color = QComboBox()
        fill_color_combo(self.color, None)
        self.color.setItemText(0, "Default")
        self.color.activated.connect(self._color)
        bar = QHBoxLayout()
        for w in (self.b_bold, self.b_it, self.b_ul, QLabel("Size"), self.size, QLabel("Color"), self.color,
                  QLabel("Justify"), *self.b_align.values()):
            bar.addWidget(w)
        bar.addStretch(1)
        hint = QLabel("Size is relative to the text height (12 pt = normal). Field codes such as {page} work.")
        hint.setStyleSheet("color:gray")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(bar); lay.addWidget(self.edit); lay.addWidget(hint); lay.addWidget(bb)
        self.edit.currentCharFormatChanged.connect(self._sync)
        self.edit.setFocus()

    def _set_align(self, key):
        self.align = key
        for k, b in self.b_align.items():
            b.setChecked(k == key)
        self.edit.setFocus()

    def _merge(self, f):
        self.edit.mergeCurrentCharFormat(f)
        self.edit.setFocus()

    def _bold(self, on):
        f = QTextCharFormat(); f.setFontWeight(700 if on else 400); self._merge(f)

    def _italic(self, on):
        f = QTextCharFormat(); f.setFontItalic(on); self._merge(f)

    def _underline(self, on):
        f = QTextCharFormat(); f.setFontUnderline(on); self._merge(f)

    def _size(self, _):
        f = QTextCharFormat(); f.setFontPointSize(BASE_PT * self.size.currentData()); self._merge(f)

    def _color(self, _):
        n = self.color.currentData()
        f = QTextCharFormat()
        if n:
            f.setProperty(COLOR_PROP, int(n)); f.setForeground(QBrush(aci_color(n)))
        else:
            f.setProperty(COLOR_PROP, 0); f.setForeground(QBrush(self.edit.palette().text().color()))
        self._merge(f)

    def _sync(self, f):
        self.b_bold.setChecked(f.fontWeight() >= 600)
        self.b_it.setChecked(f.fontItalic()); self.b_ul.setChecked(f.fontUnderline())
        pt = f.fontPointSize() or BASE_PT
        self.size.blockSignals(True)
        i = min(range(len(SIZES)), key=lambda k: abs(SIZES[k] - pt))
        self.size.setCurrentIndex(i); self.size.blockSignals(False)
        col = f.property(COLOR_PROP)
        self.color.blockSignals(True)
        self.color.setCurrentIndex(max(0, self.color.findData(int(col)) if isinstance(col, int) and col else 0))
        self.color.blockSignals(False)

    def result_markup(self):
        """-> (source, rich). Plain text stays plain (rich=False)."""
        lines = document_to_lines(self.edit)
        if all(not (r.bold or r.italic or r.underline or abs(r.size - 1) > 1e-3 or r.color)
               for ln in lines for r in ln):
            return "\n".join("".join(r.text for r in ln) for ln in lines), False
        return richtext.dumps(lines), True
