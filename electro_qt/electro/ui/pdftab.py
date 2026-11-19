"""A reference PDF shown inside a tab (Qt's PDF viewer, needs PySide6-Addons / QtPdf)."""
from __future__ import annotations
from PySide6.QtCore import QObject, QEvent, QBuffer, QByteArray, QIODevice


def available():
    try:
        from PySide6.QtPdf import QPdfDocument            # noqa: F401
        from PySide6.QtPdfWidgets import QPdfView         # noqa: F401
        return True
    except ImportError:
        return False


class _Fit(QObject):
    """Keeps the viewer the size of the tab's viewport."""

    def __init__(self, viewport, pdfview):
        super().__init__(viewport)
        self.vp, self.pv = viewport, pdfview
        viewport.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.vp and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.pv.setGeometry(self.vp.rect())
        return False


def attach(view, data: bytes):
    """Show the PDF `data` over a tab's (empty) drawing view. Returns True when the viewer could be created."""
    if not available():
        return False
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    buf = QBuffer(view)
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    doc = QPdfDocument(view)
    doc.load(buf)
    pv = QPdfView(view.viewport())
    pv.setDocument(doc)
    pv.setPageMode(QPdfView.PageMode.MultiPage)
    pv.setZoomMode(QPdfView.ZoomMode.FitToWidth)
    fit = _Fit(view.viewport(), pv)
    pv.setGeometry(view.viewport().rect())
    pv.show()
    view._pdf = (buf, doc, pv, fit)                        # keep them alive
    return True
