"""Graphics items that mirror model entities. One item per entity, data(0)=id."""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QPen, QBrush, QPainterPath, QPainterPathStroker,
                           QTransform, QFont, QFontMetricsF)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsRectItem,
                               QGraphicsEllipseItem, QGraphicsPathItem,
                               QGraphicsSimpleTextItem, QGraphicsItemGroup)
from .. import model as m

PALETTE = {1: ("Red", "#ff3b3b"), 2: ("Yellow", "#ffe14d"), 3: ("Green", "#3bd16f"),
           4: ("Cyan", "#3bd9e0"), 5: ("Blue", "#4d7dff"), 6: ("Magenta", "#d84dff"),
           7: ("White / Black", "#f2f2f2"), 8: ("Gray", "#808080"), 9: ("Light gray", "#c0c0c0"),
           10: ("Brown", "#a9672c"), 11: ("Orange", "#ff8a1f")}
THEME = {"light": False}      # set by the scene when the background is light
LINEWEIGHTS = [0.0, 0.13, 0.18, 0.25, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00]   # mm; 0 = default
HIGHLIGHT = QColor("#00e5ff")
HIT_WIDTH = 0.08          # model units; clickable corridor around thin lines


def aci_color(n: int) -> QColor:
    """Colour for a palette index. On a light background white becomes black and
    the rest are darkened a little so yellow/orange stay readable."""
    c = QColor(PALETTE.get(abs(n), (None, "#f2f2f2"))[1])
    if THEME["light"]:
        return QColor("#000000") if abs(n) == 7 else c.darker(135)
    return c


def weight_px(mm: float, is_wire: bool) -> float:
    """Screen width of a line. 0 = the built-in default (what drawings used before
    line weights existed)."""
    if mm > 0:
        return max(1.0, mm * 4.5)
    return 2.5 if is_wire else 1.5


def make_pen(entity, layers, selected=False) -> QPen:
    layer = layers.get(entity.style.layer)
    color = entity.style.color if entity.style.color is not None else (layer.color if layer else 7)
    lt = entity.style.linetype
    if lt == "continuous" and layer:
        lt = layer.linetype
    is_wire = bool(layer and layer.kind == "wire")
    pen = QPen(HIGHLIGHT if selected else aci_color(color))
    pen.setCosmetic(True)
    w = entity.style.width if entity.style.width > 0 else (layer.lineweight if layer else 0.0)
    pen.setWidthF(weight_px(w, is_wire))
    if selected:
        pen.setWidthF(pen.widthF() + 1)
    if lt in ("dashed", "dotted"):
        pen.setStyle(Qt.PenStyle.DashLine if lt == "dashed" else Qt.PenStyle.DotLine)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


class _Common:
    """Shared selection/move behaviour. Subclasses call _setup()."""

    def _setup(self, entity, layers, scene_ref):
        self.entity_id = entity.id
        self._entity = entity
        self._layers = layers
        self._scene_ref = scene_ref
        self.setData(0, entity.id)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._restyle(False)

    def _restyle(self, selected):
        pen = make_pen(self._entity, self._layers, selected)
        self.setPen(pen)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._restyle(bool(value))
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            sc = self._scene_ref()
            if sc is not None and sc.snap_settings.grid:
                step = sc.snap_settings.grid_step
                return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        return super().itemChange(change, value)


class LineItem(_Common, QGraphicsLineItem):
    def __init__(self, e: m.Line, layers, scene_ref):
        super().__init__(e.x1, e.y1, e.x2, e.y2)
        self._setup(e, layers, scene_ref)

    def shape(self):
        p = QPainterPath(self.line().p1()); p.lineTo(self.line().p2())
        s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
        return s.createStroke(p)

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen()); painter.drawLine(self.line())


class RectItem(_Common, QGraphicsRectItem):
    def __init__(self, e: m.Rect, layers, scene_ref):
        super().__init__(QRectF(e.x, e.y, e.w, e.h).normalized())
        self._setup(e, layers, scene_ref)

    def shape(self):           # outline only, so the inside stays clickable-through
        p = QPainterPath(); p.addRect(self.rect())
        s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
        return s.createStroke(p)

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen()); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())


class CircleItem(_Common, QGraphicsEllipseItem):
    def __init__(self, e: m.Circle, layers, scene_ref):
        super().__init__(e.cx - e.r, e.cy - e.r, 2 * e.r, 2 * e.r)
        self._filled = e.filled
        self._setup(e, layers, scene_ref)

    def shape(self):
        p = QPainterPath()
        if self._filled:
            p.addEllipse(self.rect().adjusted(-.03, -.03, .03, .03))
            return p
        p.addEllipse(self.rect())
        s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
        return s.createStroke(p)

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen())
        painter.setBrush(QBrush(self.pen().color()) if self._filled else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect())


class ArcItem(_Common, QGraphicsPathItem):
    def __init__(self, e: m.Arc, layers, scene_ref):
        span = (e.end - e.start) % 360 or 360
        n = max(8, int(span / 5))
        path = QPainterPath()
        for i in range(n + 1):
            a = math.radians(e.start + span * i / n)
            pt = QPointF(e.cx + e.r * math.cos(a), e.cy + e.r * math.sin(a))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        super().__init__(path)
        self._setup(e, layers, scene_ref)

    def shape(self):
        s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
        return s.createStroke(self.path())

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen()); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())


class TextItem(_Common, QGraphicsPathItem):
    """Text height = cap height in model units; baseline of the first line at (x, y).
    Drawn as a filled path so every line of a multi-line block can be justified:
    left / center / right apply to the lines AND the anchor (the block's left edge,
    middle or right edge sits on the anchor point)."""

    def __init__(self, e: m.Text, layers, scene_ref):
        super().__init__()
        font = QFont(e.font or "Sans Serif"); font.setPixelSize(100)
        fm = QFontMetricsF(font)
        lines = (e.resolved or e.source).split("\n")
        width = max((fm.horizontalAdvance(s) for s in lines), default=0.0)
        path = QPainterPath()
        for i, s in enumerate(lines):
            lw = fm.horizontalAdvance(s)
            x = {"center": (width - lw) / 2, "right": width - lw}.get(e.align, 0.0)
            path.addText(x, i * fm.lineSpacing(), font, s)
        self.setPath(path)
        dx = {"center": width / 2, "right": width}.get(e.align, 0.0)
        k = (e.height / 0.72) / 100.0
        t = QTransform()
        t.translate(e.x, e.y)
        t.rotate(e.rotation)
        t.scale(k, -k)
        t.translate(-dx, 0)
        self.setTransform(t)
        self._setup(e, layers, scene_ref)

    def shape(self):
        p = QPainterPath(); p.addRect(self.path().boundingRect())
        return p

    def boundingRect(self):
        return self.path().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(Qt.PenStyle.NoPen)); painter.setBrush(self.brush())
        painter.drawPath(self.path())

    def _restyle(self, selected):
        pen = make_pen(self._entity, self._layers, selected)
        self.setBrush(QBrush(pen.color()))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.update()


class LogoItem(QGraphicsItem):
    """The project's title-block image, fitted (aspect kept) inside a box. Not interactive."""

    def __init__(self, pixmap, box):
        super().__init__()
        self._pm, self._box = pixmap, box
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(-4)

    def boundingRect(self):
        x, y, w, h = self._box
        return QRectF(x, y, w, h)

    def paint(self, painter, option, widget=None):
        x, y, w, h = self._box
        pw, ph = self._pm.width(), self._pm.height()
        if pw <= 0 or ph <= 0:
            return
        s = min(w / pw, h / ph)
        painter.save()
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(x + w / 2, y + h / 2)
        painter.scale(s, -s)                       # view is y-up
        painter.drawPixmap(int(-pw / 2), int(-ph / 2), self._pm)
        painter.restore()


class GroupItem(QGraphicsItemGroup):
    """A group: child items are built from the group's entities; the group item
    owns selection and moving for all of them."""

    def __init__(self, e: m.Group, layers, scene_ref):
        super().__init__()
        self.entity_id = e.id
        self._scene_ref = scene_ref
        self.setData(0, e.id)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        for c in e.children:
            ch = build_item(c, layers, scene_ref)
            if ch is None:
                continue
            ch.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ch.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self.addToGroup(ch)

    def _restyle(self, selected):
        for ch in self.childItems():
            if hasattr(ch, "_restyle"):
                ch._restyle(selected)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._restyle(bool(value))
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            sc = self._scene_ref()
            if sc is not None and sc.snap_settings.grid:
                step = sc.snap_settings.grid_step
                return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        return super().itemChange(change, value)

    def shape(self):                       # outline only, not the empty interior
        path = QPainterPath()
        for ch in self.childItems():
            path.addPath(ch.mapToParent(ch.shape()))
        return path

    def paint(self, painter, option, widget=None):
        pass                               # children paint themselves; no dashed box


class SlotItem(GroupItem):
    """A wire# slot mark drawn while making a block: a small ring and the terminal name."""

    def __init__(self, e: m.SlotMark, layers, scene_ref):
        kids = [m.Circle(e.x, e.y, 0.05, m.Style("0", color=11))]
        if e.terminal:
            kids.append(m.Text(e.x, e.y - 0.12, e.terminal, e.terminal, 0.07, 0.0, m.Style("0", color=11),
                               align="center"))
        tmp = m.Group(kids)
        tmp.id = e.id
        super().__init__(tmp, layers, scene_ref)


class BlockRefItem(GroupItem):
    """One placed block: the definition's graphics (rotated / mirrored / field codes
    filled in) plus a small ring and name at each wire# slot. Moves as one object."""

    def __init__(self, e: m.BlockRef, layers, scene_ref):
        from .. import blocks as bk
        sc = scene_ref()
        proj = sc.project if sc is not None else None
        blk = proj.blocks.get(e.block) if proj is not None else None
        if blk is None:                       # definition missing: show where it is
            kids = [m.Line(e.x - 0.1, e.y, e.x + 0.1, e.y, m.Style("0", color=1)),
                    m.Line(e.x, e.y - 0.1, e.x, e.y + 0.1, m.Style("0", color=1)),
                    m.Text(e.x + 0.12, e.y, e.block, e.block, 0.08, 0.0, m.Style("0", color=1))]
        else:
            kids = bk.resolved_entities(proj, sc.sheet, blk, e)
            for i, (slot, (x, y)) in enumerate(bk.block_slots(blk, e)):
                kids.append(m.Circle(x, y, 0.03, m.Style("0", color=11)))
                name = bk.slot_name(e, i, slot)
                if name:
                    kids.append(m.Text(x, y - 0.1, name, name, 0.06, 0.0, m.Style("0", color=8), align="center"))
        tmp = m.Group(kids)
        tmp.id = e.id
        super().__init__(tmp, layers, scene_ref)

    def shape(self):                          # the whole body is clickable
        p = QPainterPath()
        p.addRect(self.childrenBoundingRect().adjusted(-0.05, -0.05, 0.05, 0.05))
        return p


def build_item(e, layers, scene_ref):
    if isinstance(e, m.BlockRef): return BlockRefItem(e, layers, scene_ref)
    if isinstance(e, m.SlotMark): return SlotItem(e, layers, scene_ref)
    if isinstance(e, m.Group): return GroupItem(e, layers, scene_ref)
    if isinstance(e, m.Line): return LineItem(e, layers, scene_ref)
    if isinstance(e, m.Rect): return RectItem(e, layers, scene_ref)
    if isinstance(e, m.Circle): return CircleItem(e, layers, scene_ref)
    if isinstance(e, m.Arc): return ArcItem(e, layers, scene_ref)
    if isinstance(e, m.Text): return TextItem(e, layers, scene_ref)
    return None
