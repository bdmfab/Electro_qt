"""Panel layout tools: insert a DIN rail / wire duct (1 in long, then drag the ends), place a part from
the schematic, with smart edge / DIN rail centre line snapping. Space turns the object being placed."""
from __future__ import annotations
from PySide6.QtCore import Qt, QLineF, QPointF, QRectF
from PySide6.QtGui import QColor, QPen
from .. import model as m
from .. import panel as pn
from .tools import Tool, PREVIEW


class PanelPlaceTool(Tool):
    """name 'panel': places scene.panel_spec (kind plate / rail / duct / part) at the clicked point."""
    name = "panel"

    def __init__(self, scene):
        super().__init__(scene)
        s = scene.panel_spec or {}
        self.ghost = m.PanelObj(s.get("kind", "rail"), 0.0, 0.0, s.get("w", 1.0), s.get("h", 1.378), scene.panel_rot,
                                depth=s.get("depth", 0.0), block=s.get("block", ""), tag=s.get("tag", ""),
                                mount=s.get("mount", ""), cl=s.get("cl", 0.0), qty=s.get("qty", 1),
                                ident=s.get("ident", ""), first=s.get("first", 1),
                                style=m.Style(layer=scene.panel_layer(s.get("kind", "rail"))))
        self.guides, self.snapped_rail = [], None

    def hint(self):
        g = self.ghost
        what = g.tag or (f"{g.qty} x {g.block}" if g.kind == "terminals" else g.block) or pn.KIND_NAMES[g.kind]
        return f"Place {what}: click to drop. Space turns it, Esc / right-click cancels"

    def _place(self):
        sc, g = self.scene, self.ghost
        objs = pn.panel_objects(sc.sheet.entities)
        tol = 10.0 / sc.view_scale
        x, y = sc.raw
        self.guides, self.snapped_rail = [], None
        if g.kind in pn.MOUNTED and g.mount == "rail":
            r = pn.rail_snap(objs, g, x, y, tol=max(0.5, 30.0 / sc.view_scale))
            if r is not None:
                cx, cy, rot, rail = r
                g.rot = rot
                self.snapped_rail = rail
                i = 0 if pn.axis(rail) == "x" else 1
                w, h = pn.size(g)
                v, guide = pn.snap_line(objs, i, (cx, cy)[i] - (w if i == 0 else h) / 2, tol, sc.panel_gap)
                if guide is not None:                      # the part's low edge lines up with a neighbour
                    cx, cy = (v + w / 2, cy) if i == 0 else (cx, v + h / 2)
                    self.guides.append(("v" if i == 0 else "h", guide))
                g.cx, g.cy = cx, cy
                return
        g.cx, g.cy = self.cur
        w, h = pn.size(g)
        g.cx, g.cy, self.guides = pn.snap_box(objs, g.cx, g.cy, w, h, tol, sc.panel_gap)

    def move(self, pt):
        self.cur = pt
        self._place()

    def key(self, ev):
        if ev.key() in (Qt.Key.Key_Space, Qt.Key.Key_R):
            self.ghost.rot = (self.ghost.rot + (180 if self.snapped_rail is not None else 90)) % 360
            self.scene.panel_rot = self.ghost.rot
            self._place()
            return True
        return False

    def press(self, pt):
        sc, g = self.scene, self.ghost
        self._place()
        new = m.PanelObj(g.kind, g.cx, g.cy, g.w, g.h, g.rot, depth=g.depth, block=g.block, tag=g.tag,
                         mount=g.mount, cl=g.cl, qty=g.qty, ident=g.ident, first=g.first, style=m.Style(layer=sc.panel_layer(g.kind)))
        sc.add_entities([new], f"Place {pn.KIND_NAMES[g.kind].lower()}")
        sc.tool_done()
        sc._select_entities([new])
        sc.panel_placed.emit()

    def paint(self, p, vs):
        g = self.ghost
        x0, y0, x1, y1 = pn.box(g)
        p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        if g.kind in pn.MOUNTED and g.mount == "rail":
            ox, oy = pn.centerline_offset(g)
            p.setPen(QPen(QColor("#ff8a1f"), 0, Qt.PenStyle.DashDotLine))
            if pn.axis(g) == "x":
                p.drawLine(QLineF(x0, g.cy + oy, x1, g.cy + oy))
            else:
                p.drawLine(QLineF(g.cx + ox, y0, g.cx + ox, y1))
        p.setPen(QPen(QColor("#ff2fd0"), 0, Qt.PenStyle.DashLine))
        pad = 2.0
        for kind, v in self.guides:
            if kind == "v":
                p.drawLine(QLineF(v, y0 - pad, v, y1 + pad))
            else:
                p.drawLine(QLineF(x0 - pad, v, x1 + pad, v))
        w, h = pn.size(g)
        self.scene.draw_label(p, (x1, y1), f"{w:.3f} x {h:.3f}", vs)


class DimTool(Tool):
    """Horizontal / vertical dimension: pick two points, then click where the dimension line goes.
    The direction follows the two points (Space switches horizontal <-> vertical)."""
    name = "dim"

    def __init__(self, scene):
        super().__init__(scene)
        self.pts = []
        self.flip = False

    def hint(self):
        return ("Dimension: pick the first point", "Dimension: pick the second point",
                "Dimension: click where the line goes (Space: horizontal / vertical)")[len(self.pts)]

    def _orient(self):
        o = pn.dim_auto_orient(self.pts[0], self.pts[1])
        return ("v" if o == "h" else "h") if self.flip else o

    def _dim(self):
        o = self._orient()
        pos = self.cur[1] if o == "h" else self.cur[0]
        return m.Dim(*self.pts[0], *self.pts[1], o, pos)

    def press(self, pt):
        if len(self.pts) < 2:
            if self.pts and abs(pt[0] - self.pts[0][0]) < 1e-9 and abs(pt[1] - self.pts[0][1]) < 1e-9:
                return
            self.pts.append(pt)
            self.scene.prompt.emit(self.hint())
            return
        sc = self.scene
        d = self._dim()
        d.style = m.Style(layer=sc.panel_layer("dim"))
        sc.add_entities([d], "Dimension")
        sc.tool_done()
        sc._select_entities([d])

    def key(self, ev):
        if ev.key() in (Qt.Key.Key_Space,) and len(self.pts) == 2:
            self.flip = not self.flip
            return True
        return False

    def cancel(self):
        self.pts = []
        super().cancel()

    def paint(self, p, vs):
        p.setPen(self._pen())
        if len(self.pts) == 1:
            p.drawLine(QLineF(QPointF(*self.pts[0]), QPointF(*self.cur)))
        elif len(self.pts) == 2:
            d = self._dim()
            a, b = pn.dim_line(d)
            for q, e in (((d.x1, d.y1), a), ((d.x2, d.y2), b)):
                p.drawLine(QLineF(QPointF(*q), QPointF(*e)))
            p.drawLine(QLineF(QPointF(*a), QPointF(*b)))
            self.scene.draw_label(p, self.cur, pn.dim_text(pn.dim_value(d), self.scene.sheet.dim_units), vs)
