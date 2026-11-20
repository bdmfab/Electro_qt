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


def _drag_pos(ss, value):
    """Where a dragged object may go: ortho keeps the drag on one axis (whether or not the grid snaps),
    the grid rounds what is left."""
    x, y = value.x(), value.y()
    if ss.ortho:
        if abs(x) >= abs(y):
            y = 0.0
        else:
            x = 0.0
    if ss.grid:
        step = ss.grid_step
        x, y = round(x / step) * step, round(y / step) * step
    return QPointF(x, y)



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
            if sc is not None:
                return self._snap_move(sc, _drag_pos(sc.snap_settings, value))
        return super().itemChange(change, value)

    def _snap_move(self, sc, v):
        return v


class LineItem(_Common, QGraphicsLineItem):
    def __init__(self, e: m.Line, layers, scene_ref):
        super().__init__(e.x1, e.y1, e.x2, e.y2)
        self._shape = None
        self._setup(e, layers, scene_ref)

    def shape(self):                       # (cached: asked for constantly while selecting / repainting)
        if self._shape is None:
            p = QPainterPath(self.line().p1()); p.lineTo(self.line().p2())
            s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
            self._shape = s.createStroke(p)
        return self._shape

    def boundingRect(self):
        if getattr(self, "_bounds", None) is None:
            self._bounds = self.shape().boundingRect()
        return self._bounds

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


PANEL_COLORS = {"plate": ("#3a4048", "#e9ecef"), "rail": ("#8aa0b8", "#9db2c8"),
                "duct": ("#c9b458", "#e3d28a"), "part": ("#4f8fd0", "#a9cdf0"),
                "terminals": ("#3fae8f", "#9fdcc9")}      # (dark, light) fill


class PanelItem(_Common, QGraphicsRectItem):
    """A panel layout object (back plate, DIN rail, wire duct, part footprint) drawn to scale: its box, its
    label, a part's DIN rail centre line and a small lock mark on a locked rail / duct."""

    def __init__(self, e: m.PanelObj, layers, scene_ref):
        from .. import panel as pn
        x0, y0, x1, y1 = pn.box(e)
        super().__init__(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.setZValue({"plate": -10, "rail": -5, "duct": -4}.get(e.kind, 0))
        self._setup(e, layers, scene_ref)
        if e.locked:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def shape(self):
        p = QPainterPath()
        p.addRect(self.rect())
        if self._entity.kind == "plate":             # only the edge: the plate must not swallow clicks on what is on it
            s = QPainterPathStroker(); s.setWidth(HIT_WIDTH * 2)
            return s.createStroke(p)
        return p

    def boundingRect(self):
        return self.rect().adjusted(-0.05, -0.05, 0.05, 0.05)

    def _label(self):
        from .. import panel as pn
        e = self._entity
        if e.kind == "terminals":
            return e.block, f"x{e.qty}"
        if e.kind == "part":
            return e.tag or e.block, e.block if e.tag and e.block != e.tag else ""
        if e.kind == "rail":
            return "DIN rail", ""
        if e.kind == "duct":
            return f"Duct {e.h:g} x {e.depth:g}" if e.depth else "Duct", ""
        return pn.KIND_NAMES["plate"], f"{e.w:g} x {e.h:g}"

    def _snap_move(self, sc, v):
        """While dragging on the panel layout, the selection's edges / centres snap to the other objects (or sit
        the panel gap away from their sides). Every selected item computes the same answer from the same drag."""
        from .. import panel as pn
        if not sc.sheet.panel:
            return v
        sel = [e for e in sc.selected_entities() if isinstance(e, m.PanelObj)]
        if not sel:
            return v
        bx = [pn.box(e) for e in sel]
        x0, y0 = min(b[0] for b in bx), min(b[1] for b in bx)
        x1, y1 = max(b[2] for b in bx), max(b[3] for b in bx)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        nx, ny, _ = pn.snap_box(pn.panel_objects(sc.sheet.entities), cx + v.x(), cy + v.y(), x1 - x0, y1 - y0,
                                10.0 / sc.view_scale, sc.panel_gap, exclude=sel)
        dx, dy = nx - cx, ny - cy
        if sc.snap_settings.ortho:                      # stay on the drag's axis
            if v.y() == 0:
                dy = 0.0
            else:
                dx = 0.0
        return QPointF(dx, dy)

    def _cells(self):
        e = self._entity
        return e.kind == "terminals" or (e.kind == "part" and not e.tag and (e.ident or e.names or e.first != 1))

    def _paint_cells(self, painter, r, e, pn):
        """Each terminal of a stack carries its own label (TB1.1 ...); the identifier sits above the stack."""
        txt_col = QColor("#000000" if THEME["light"] else "#ffffff")
        labels = pn.terminal_labels(e)
        n = len(labels)
        if pn.axis(e) == "x":
            cw = r.width() / n
            cells = [QRectF(r.left() + i * cw, r.top(), cw, r.height()) for i in range(n)]
        else:
            ch = r.height() / n
            cells = [QRectF(r.left(), r.top() + i * ch, r.width(), ch) for i in range(n)]
        for c, t in zip(cells, labels):
            self._text(painter, t, c, 0.0, 0.5, txt_col, vertical=c.width() < c.height() * 0.6)
        if e.ident and n > 1:
            self._text(painter, f"{e.ident}  ({e.block})", QRectF(r.left(), r.bottom(), r.width(), 0.2), 0.0, 0.8, txt_col)

    def paint(self, painter, option, widget=None):
        from .. import panel as pn
        e, r = self._entity, self.rect()
        dark, light = PANEL_COLORS.get(e.kind, PANEL_COLORS["part"])
        fill = QColor(light if THEME["light"] else dark)
        fill.setAlpha(0 if e.kind == "plate" else 150)
        painter.setPen(self.pen()); painter.setBrush(fill)
        painter.drawRect(r)
        if e.kind == "terminals" and e.qty > 1:               # the stacked blocks, side by side
            n = e.qty
            painter.setPen(QPen(self.pen().color(), 0, Qt.PenStyle.SolidLine))
            for i in range(1, n):
                if pn.axis(e) == "x":
                    x = r.left() + r.width() * i / n
                    painter.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
                else:
                    y = r.top() + r.height() * i / n
                    painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        if e.kind in pn.MOUNTED and e.mount == "rail":       # the DIN rail centre line through the part
            ox, oy = pn.centerline_offset(e)
            pen = QPen(QColor("#ff8a1f"), 0, Qt.PenStyle.DashDotLine)
            painter.setPen(pen)
            if pn.axis(e) == "x":
                painter.drawLine(QPointF(r.left(), e.cy + oy), QPointF(r.right(), e.cy + oy))
            else:
                painter.drawLine(QPointF(e.cx + ox, r.top()), QPointF(e.cx + ox, r.bottom()))
        if e.kind in ("rail", "duct"):                         # the long centre line
            painter.setPen(QPen(QColor("#555d66" if THEME["light"] else "#cfd6de"), 0, Qt.PenStyle.DotLine))
            a, b = pn.end_points(e)
            painter.drawLine(QPointF(*a), QPointF(*b))
        main, sub = self._label()
        if self._cells():
            return self._paint_cells(painter, r, e, pn)
        txt_col = QColor("#000000" if THEME["light"] else "#ffffff")
        self._text(painter, main, r, 0.0 if not sub else 0.18, 0.5 if not sub else 0.32, txt_col)
        if sub:
            self._text(painter, sub, r, -0.18, 0.2, txt_col)
        if e.locked:
            painter.setPen(QPen(txt_col, 0)); painter.setBrush(Qt.BrushStyle.NoBrush)
            if e.kind in ("rail", "duct"):
                pts = pn.end_points(e)
            else:                                              # a small ring in the corner
                x0, y0, x1, y1 = pn.box(e)
                pts = [(x0 + 0.08, y1 - 0.08)]
            for q in pts:
                painter.drawEllipse(QPointF(*q), 0.05, 0.05)

    @staticmethod
    def _text(painter, text, r, dy_frac, hfrac, color, vertical=False):
        """Upright label centred in the box (dy_frac / hfrac: share of the box height), shrunk to fit."""
        if not text:
            return
        font = QFont("Sans Serif"); font.setPixelSize(100)
        path = QPainterPath(); path.addText(0, 0, font, text)
        tb = path.boundingRect()
        if tb.width() <= 0:
            return
        along, across = (r.height(), r.width()) if vertical else (r.width(), r.height())
        k = min(across * hfrac / 72.0, along * 0.9 / tb.width(), 0.3 / 72.0)
        k = max(k, 0.001)
        t = QTransform()
        t.translate(r.center().x(), r.center().y() + dy_frac * r.height())
        if vertical:
            t.rotate(90)
        t.scale(k, -k)
        t.translate(-tb.center().x(), -tb.center().y())
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(color)
        painter.drawPath(t.map(path))
        painter.restore()



class DimItem(_Common, QGraphicsPathItem):
    """A horizontal / vertical dimension: extension lines, the dimension line with arrow heads and the
    value (inches, or millimetres when the sheet's units are mm)."""
    TEXT_H = 0.14                     # text height, inches
    ARROW = 0.12

    def __init__(self, e: m.Dim, layers, scene_ref):
        super().__init__()
        sc = scene_ref()
        units = sc.sheet.dim_units if sc is not None else "in"
        th = e.th or (sc.sheet.dim_th if sc is not None else self.TEXT_H)
        arrow = self.ARROW * th / self.TEXT_H
        from .. import panel as pn
        a, b = pn.dim_line(e)
        lines, arrows = QPainterPath(), QPainterPath()
        gap, over = 0.05, 0.08
        for p, q in (((e.x1, e.y1), a), ((e.x2, e.y2), b)):          # extension lines
            dx, dy = q[0] - p[0], q[1] - p[1]
            d = math.hypot(dx, dy)
            if d > gap:
                ux, uy = dx / d, dy / d
                lines.moveTo(p[0] + ux * gap, p[1] + uy * gap)
                lines.lineTo(q[0] + ux * over, q[1] + uy * over)
        lines.moveTo(*a); lines.lineTo(*b)                            # dimension line
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-9:
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            for tip, s in ((a, 1.0), (b, -1.0)):
                bx, by = tip[0] + s * ux * arrow, tip[1] + s * uy * arrow
                nx, ny = -uy * arrow * 0.25, ux * arrow * 0.25
                arrows.moveTo(*tip); arrows.lineTo(bx + nx, by + ny); arrows.lineTo(bx - nx, by - ny); arrows.closeSubpath()
        text = QPainterPath()
        font = QFont("Sans Serif"); font.setPixelSize(100)
        tp = QPainterPath(); tp.addText(0, 0, font, pn.dim_text(pn.dim_value(e), units))
        tb = tp.boundingRect()
        if tb.width() > 0:
            k = th / 72.0
            t = QTransform()
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if e.orient == "h":
                t.translate(mx, my + 0.05)
                t.scale(k, -k); t.translate(-tb.center().x(), 0)
            else:                                        # vertical: reads bottom to top, left of the line
                t.translate(mx - 0.05, my)
                t.rotate(90)
                t.scale(k, -k); t.translate(-tb.center().x(), 0)
            text = t.map(tp)
        self._lines, self._arrows, self._text = lines, arrows, text
        whole = QPainterPath(lines); whole.addPath(arrows); whole.addPath(text)
        self.setPath(whole)
        self._setup(e, layers, scene_ref)

    def shape(self):
        s = QPainterPathStroker(); s.setWidth(HIT_WIDTH)
        p = s.createStroke(self._lines)
        p.addRect(self._text.boundingRect())
        return p

    def boundingRect(self):
        return self.path().boundingRect().adjusted(-0.1, -0.1, 0.1, 0.1)

    def paint(self, painter, option, widget=None):
        pen = self.pen()
        painter.setPen(pen)
        painter.drawPath(self._lines)
        painter.setBrush(pen.color()); painter.drawPath(self._arrows)
        painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(self._text)



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
        txt = "" if getattr(e, "hidden", False) else (e.resolved or e.source)
        self._parts = None
        if getattr(e, "rich", False):
            path, width = self._rich_path(e, txt, font, fm)
        else:
            lines = txt.split("\n")
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

    def _rich_path(self, e, txt, base_font, base_fm):
        """Formatted text: each run is its own path (bold / italic / size / underline / colour)."""
        from .. import richtext
        fam = e.font or "Sans Serif"
        layout, widths = [], []
        for runs in richtext.parse(txt):
            pieces, w = [], 0.0
            for r in runs:
                f = QFont(r.font or fam); f.setPixelSize(max(1, int(round(100 * r.size))))
                f.setBold(r.bold); f.setItalic(r.italic)
                adv = QFontMetricsF(f).horizontalAdvance(r.text)
                pieces.append((r, f, adv)); w += adv
            layout.append((pieces, max((r.size for r in runs), default=1.0)))
            widths.append(w)
        width = max(widths, default=0.0)
        parts, total, y = [], QPainterPath(), 0.0
        for li, (pieces, big) in enumerate(layout):
            if li:
                y += base_fm.lineSpacing() * big * getattr(e, "spacing", 1.0)
            x = {"center": (width - widths[li]) / 2, "right": width - widths[li]}.get(e.align, 0.0)
            for r, f, adv in pieces:
                p = QPainterPath(); p.addText(x, y, f, r.text)
                if r.underline:
                    px = f.pixelSize()
                    p.addRect(x, y + 0.12 * px, adv, max(1.0, 0.06 * px))
                parts.append((p, aci_color(r.color) if r.color else None))
                total.addPath(p)
                x += adv
        self._parts = parts
        return total, width

    def shape(self):
        p = QPainterPath(); p.addRect(self.path().boundingRect())
        return p

    def boundingRect(self):
        return self.path().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        if self._parts:
            for p, c in self._parts:
                painter.setBrush(QBrush(c) if c is not None else self.brush())
                painter.drawPath(p)
            return
        painter.setBrush(self.brush())
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

    def aspect(self):
        return self._pm.width() / max(1, self._pm.height())

    def fitted(self):
        """(x, y, w, h) of the picture itself: the box with the aspect ratio kept."""
        x, y, w, h = self._box
        a = self.aspect()
        fw, fh = (w, w / a) if w / a <= h else (h * a, h)
        return (x + (w - fw) / 2, y + (h - fh) / 2, fw, fh)

    def set_box(self, box):
        self.prepareGeometryChange()
        self._box = tuple(box)
        self.update()

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
            if sc is not None:
                return self._snap_move(sc, _drag_pos(sc.snap_settings, value))
        return super().itemChange(change, value)

    def _snap_move(self, sc, v):
        return v

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

    SOLID_MAX = 1.5                           # inches: bigger blocks are picked by their lines, not their inside

    def shape(self):
        r = self.childrenBoundingRect()
        if max(r.width(), r.height()) > self.SOLID_MAX:
            return super().shape()            # a PLC across the page must not hide what lies under it
        p = QPainterPath()                    # a small part: the whole body is clickable
        p.addRect(r.adjusted(-0.05, -0.05, 0.05, 0.05))
        return p


def build_item(e, layers, scene_ref):
    if isinstance(e, m.BlockRef): return BlockRefItem(e, layers, scene_ref)
    if isinstance(e, m.SlotMark): return SlotItem(e, layers, scene_ref)
    if isinstance(e, m.Group): return GroupItem(e, layers, scene_ref)
    if isinstance(e, m.Line): return LineItem(e, layers, scene_ref)
    if isinstance(e, m.PanelObj): return PanelItem(e, layers, scene_ref)
    if isinstance(e, m.Dim): return DimItem(e, layers, scene_ref)
    if isinstance(e, m.Rect): return RectItem(e, layers, scene_ref)
    if isinstance(e, m.Circle): return CircleItem(e, layers, scene_ref)
    if isinstance(e, m.Arc): return ArcItem(e, layers, scene_ref)
    if isinstance(e, m.Text): return TextItem(e, layers, scene_ref)
    return None
