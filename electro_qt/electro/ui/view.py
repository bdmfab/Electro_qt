from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QTransform
from PySide6.QtWidgets import QGraphicsView
from ..geometry import bounds


class EditorView(QGraphicsView):
    MIN_SCALE, MAX_SCALE = 8.0, 4000.0     # pixels per inch

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setMouseTracking(True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)   # select tool is the default
        self._pan = None
        self._fitted = False
        self.set_scale(80.0)
        self.centerOn(4, 5)

    def set_scale(self, s):
        s = max(self.MIN_SCALE, min(self.MAX_SCALE, s))
        self.setTransform(QTransform.fromScale(s, -s))      # y-up model coordinates
        self.scene().view_scale = s

    def wheelEvent(self, ev):
        f = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
        self.set_scale(self.scene().view_scale * f)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._pan = ev.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept(); return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._pan is not None:
            d = ev.position() - self._pan
            self._pan = ev.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            ev.accept(); return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton and self._pan is not None:
            self._pan = None
            sel = self.scene().tool.name == "select"
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor if sel else Qt.CursorShape.CrossCursor)
            ev.accept(); return
        super().mouseReleaseEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not self._fitted and self.viewport().width() > 200:    # first real size: fit the sheet
            self._fitted = True
            self.zoom_extents()

    def zoom_extents(self):
        sh = self.scene().sheet
        b = (0.0, 0.0, sh.width, sh.height)
        ents = bounds(sh.entities, getattr(self.scene(), 'project', None) and self.scene().project.blocks)
        if ents:
            b = (min(b[0], ents[0]), min(b[1], ents[1]), max(b[2], ents[2]), max(b[3], ents[3]))
        w, h = max(b[2] - b[0], 0.5), max(b[3] - b[1], 0.5)
        vw, vh = self.viewport().width(), self.viewport().height()
        self.set_scale(min(vw / w, vh / h) * 0.9)
        self.centerOn((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
