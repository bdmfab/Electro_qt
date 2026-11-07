"""PDF export: every sheet drawn the way it looks on screen, on white with dark lines
(vector, no grid, no editing marks). One QPdfWriter per file; the merged file has one page per sheet."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QSizeF, QMarginsF
from PySide6.QtGui import QColor, QPainter, QPdfWriter, QPageSize, QPageLayout
from .items import THEME
from .scene import EditorScene

RES = 96                     # painter units per inch (the PDF itself is vector)


def _inches(sheet):
    k = 1.0 if sheet.units == "in" else 1 / 25.4
    return sheet.width * k, sheet.height * k


def _layout(sheet):
    unit = QPageSize.Unit.Inch if sheet.units == "in" else QPageSize.Unit.Millimeter
    return QPageLayout(QPageSize(QSizeF(sheet.width, sheet.height), unit), QPageLayout.Orientation.Portrait,
                       QMarginsF(0, 0, 0, 0))


def draw_sheet(painter: QPainter, project, sheet) -> None:
    old = THEME["light"]
    THEME["light"] = True                         # dark lines on white
    try:
        sc = EditorScene(project, sheet)
        sc.printing = True
        sc.bg = QColor("white")
        sc.show_grid = False
        sc.view_scale = RES
        wi, hi = _inches(sheet)
        W, H = wi * RES, hi * RES
        painter.save()
        painter.translate(0, H)
        painter.scale(1, -1)                      # model coordinates are y-up
        sc.render(painter, QRectF(0, 0, W, H), QRectF(0, 0, sheet.width, sheet.height),
                  Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.restore()
        sc.clear()
        sc.deleteLater()
    finally:
        THEME["light"] = old


def write_pdf(path: str, project, sheets, title: str = "") -> None:
    w = QPdfWriter(path)
    w.setResolution(RES)
    w.setTitle(title)
    w.setCreator("Electro_qt")
    painter = None
    try:
        for sh in sheets:
            w.setPageLayout(_layout(sh))
            if painter is None:
                painter = QPainter(w)
            else:
                w.newPage()
            draw_sheet(painter, project, sh)
    finally:
        if painter is not None:
            painter.end()
