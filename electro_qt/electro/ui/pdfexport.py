"""PDF export: every sheet drawn the way it looks on screen, on white with dark lines
(vector, no grid, no editing marks). One QPdfWriter per file; the merged file has one page per sheet."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QSizeF, QMarginsF
from PySide6.QtGui import QColor, QPainter, QPdfWriter, QPageSize, QPageLayout
from .. import model as m
from .items import THEME
from .scene import EditorScene

RES = 96                     # painter units per inch (the PDF itself is vector)


def _inches(sheet):
    k = 1.0 if sheet.units == "in" else 1 / 25.4
    return sheet.width * k, sheet.height * k


def _layout(sheet):
    if sheet.panel:                                # panel layouts print on an 11x17 landscape page
        return QPageLayout(QPageSize(QSizeF(17.0, 11.0), QPageSize.Unit.Inch), QPageLayout.Orientation.Portrait,
                           QMarginsF(0, 0, 0, 0))
    unit = QPageSize.Unit.Inch if sheet.units == "in" else QPageSize.Unit.Millimeter
    return QPageLayout(QPageSize(QSizeF(sheet.width, sheet.height), unit), QPageLayout.Orientation.Portrait,
                       QMarginsF(0, 0, 0, 0))


def draw_panel(painter: QPainter, project, sheet) -> None:
    """A panel layout on an 11x17 page: border + title block, the whole drawing (plate, rails, ducts, parts,
    dimensions) scaled uniformly to fit the drawing area and centred. The layout itself is not changed."""
    from ..templates import panel_pdf_sheet, PANEL_DRAWING_AREA
    from .. import fields
    page = panel_pdf_sheet(sheet)
    fields.refresh_sheet(project, page)           # the page is not in the project: fill {job}, {page}, {title1} ... itself
    draw_sheet(painter, project, page, panel_frame=True)
    old = THEME["light"]
    THEME["light"] = True
    try:
        sc = EditorScene(project, sheet)
        sc.printing = True
        sc.bg = QColor("white")
        sc.show_grid = False
        bb = sc.itemsBoundingRect()
        if bb.isEmpty():
            return
        L, B, R, T = PANEL_DRAWING_AREA
        aw, ah = R - L, T - B
        k = min(aw / bb.width(), ah / bb.height())          # page inches per model unit
        w, h = bb.width() * k, bb.height() * k
        x0, y0 = L + (aw - w) / 2, B + (ah - h) / 2
        sc.view_scale = RES * k                              # hairlines keep their printed weight
        painter.save()
        painter.translate(0, 11.0 * RES)
        painter.scale(1, -1)
        sc.render(painter, QRectF(x0 * RES, y0 * RES, w * RES, h * RES), bb, Qt.AspectRatioMode.KeepAspectRatio)
        painter.restore()
        sc.clear()
        sc.deleteLater()
    finally:
        THEME["light"] = old


def draw_sheet(painter: QPainter, project, sheet, panel_frame=False) -> None:
    if sheet.panel and not panel_frame:
        return draw_panel(painter, project, sheet)
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
        src = QRectF(0, 0, sheet.width, sheet.height)
        from ..blocks import bounds
        try:
            bb = bounds([e for e in sheet.frame if not isinstance(e, m.Text)]) if sheet.frame else None
        except Exception:
            bb = None
        if bb is not None:                                # centre the drawn frame (border + title block) on the page
            src.translate((bb[0] + bb[2]) / 2 - sheet.width / 2, (bb[1] + bb[3]) / 2 - sheet.height / 2)
        sc.render(painter, QRectF(0, 0, W, H), src, Qt.AspectRatioMode.IgnoreAspectRatio)
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
