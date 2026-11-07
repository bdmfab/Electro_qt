"""Drawing tools. Each tool receives already-snapped points from the scene
(scene.raw holds the unsnapped cursor for pick-style tools). When a tool has done
its job it calls scene.tool_done(), which returns to Select."""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, QLineF, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QInputDialog
from .. import model as m
from ..geometry import (point_on_line_at, trim_line, trim_circle, trim_arc, arc_from_ends, fillet_lines, chamfer_lines,
                        dist_point_segment, bounds, grips_of, snapshot, restore, stretch,
                        clamp_delta, multiline_wires)
from ..snap import snap_to_grid
from ..geometry import increment_number
from .. import blocks as bk
from ..geometry import arc_extent_points, text_extent, translate as _translate
import copy as _copy
from . import clipboard
from .commands import EditCmd, StretchCmd, AddBundleCmd
from ..junctions import trim_wire_start
from .items import aci_color

PREVIEW = QColor("#7dd3fc")


class Tool:
    name = ""
    anchor = None           # lets the snapper constrain to ortho from this point

    def __init__(self, scene):
        self.scene = scene
        self.typed = ""
        self.cur = (0.0, 0.0)

    def hint(self): return ""
    def press(self, pt): pass
    def release(self, pt): pass
    def move(self, pt): self.cur = pt
    def finish(self): self.cancel()
    def cancel(self): self.typed = ""
    def paint(self, p, vs): pass
    def commit_typed(self, v): pass

    def commit_values(self, vals):
        self.commit_typed(vals[0])

    def key(self, ev) -> bool:
        """Typed numeric entry (Enter or Space commits; a comma separates two values).
        Returns True if consumed."""
        k, t = ev.key(), ev.text()
        if t and (t.isdigit() or t in ".,"):
            self.typed += t; return True
        if k == Qt.Key.Key_Backspace and self.typed:
            self.typed = self.typed[:-1]; return True
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.typed:
            try:
                vals = [float(x) for x in self.typed.split(",") if x.strip()]
            except ValueError:
                vals = []
            self.typed = ""
            if vals and min(vals) >= 0:
                self.commit_values(vals)
            return True
        return False

    def _pen(self):
        return QPen(PREVIEW, 0, Qt.PenStyle.DashLine)


class SelectTool(Tool):
    name = "select"

    def hint(self):
        last = f"   Right-click empty space / Space repeats: {self.scene.last_tool}" if self.scene.last_tool else ""
        return "Select: click or drag a box; drag to move; Del deletes; double-click text to edit" + last


class LineTool(Tool):
    name = "line"

    def __init__(self, scene):
        super().__init__(scene)
        self.start = None

    @property
    def anchor(self): return self.start
    @anchor.setter
    def anchor(self, v): pass

    def hint(self):
        if self.start is None:
            return "Line: click start point"
        return "Line: click next point, or type a length + Enter/Space. Right-click / Esc ends"

    def press(self, pt):
        if self.start is None:
            self.start = pt
        else:
            self._commit(pt)

    def _commit(self, end):
        if end == self.start:
            return
        self.scene.add_entities([m.Line(*self.start, *end, self.scene.new_style())], "Line")
        self.start = end          # chain: keep drawing from the end

    def commit_typed(self, v):
        if self.start is not None and v > 0:
            self._commit(point_on_line_at(self.start, self.cur, v))

    def cancel(self): self.start = None; self.typed = ""

    def paint(self, p, vs):
        if self.start is None:
            return
        end = self.cur
        if self.typed:
            try:
                end = point_on_line_at(self.start, self.cur, float(self.typed))
            except ValueError:
                pass
        p.setPen(self._pen())
        p.drawLine(QLineF(self.start[0], self.start[1], end[0], end[1]))
        length = math.hypot(end[0] - self.start[0], end[1] - self.start[1])
        self.scene.draw_label(p, self.cur, f"{self.typed}_" if self.typed else f"{length:.3f}", vs)


class RectTool(Tool):
    name = "rect"

    def __init__(self, scene):
        super().__init__(scene); self.c1 = None

    def hint(self):
        return "Rectangle: click first corner" if self.c1 is None else "Rectangle: click opposite corner"

    def press(self, pt):
        if self.c1 is None:
            self.c1 = pt
        elif pt[0] != self.c1[0] and pt[1] != self.c1[1]:
            x0, y0 = min(pt[0], self.c1[0]), min(pt[1], self.c1[1])
            self.scene.add_entities([m.Rect(x0, y0, abs(pt[0] - self.c1[0]),
                                            abs(pt[1] - self.c1[1]), self.scene.new_style())], "Rectangle")
            self.scene.tool_done()

    def cancel(self): self.c1 = None; self.typed = ""

    def paint(self, p, vs):
        if self.c1:
            p.setPen(self._pen())
            p.drawRect(QRectF(QPointF(*self.c1), QPointF(*self.cur)).normalized())
            self.scene.draw_label(p, self.cur,
                                  f"{abs(self.cur[0]-self.c1[0]):.3f} x {abs(self.cur[1]-self.c1[1]):.3f}", vs)


class CircleTool(Tool):
    name = "circle"

    def __init__(self, scene):
        super().__init__(scene); self.center = None

    def hint(self):
        return ("Circle: click center" if self.center is None
                else "Circle: click radius point, or type radius + Enter/Space")

    def _make(self, r):
        if r > 0:
            self.scene.add_entities([m.Circle(*self.center, r, self.scene.new_style())], "Circle")
            self.scene.tool_done()

    def press(self, pt):
        if self.center is None:
            self.center = pt
        else:
            self._make(math.hypot(pt[0] - self.center[0], pt[1] - self.center[1]))

    def commit_typed(self, v):
        if self.center is not None:
            self._make(v)

    def cancel(self): self.center = None; self.typed = ""

    def paint(self, p, vs):
        if self.center:
            r = float(self.typed) if self.typed.replace(".", "", 1).isdigit() else \
                math.hypot(self.cur[0] - self.center[0], self.cur[1] - self.center[1])
            p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(*self.center), r, r)
            self.scene.draw_label(p, self.cur, f"R {r:.3f}", vs)


class ArcTool(Tool):
    """Click the two ends, then move the centre: the radius follows and stops at a half
    circle. Click to finish."""
    name = "arc"

    def __init__(self, scene):
        super().__init__(scene); self.pts = []; self.side = 1

    def hint(self):
        return ("Arc: click the first end", "Arc: click the second end",
                "Arc: move the center to set the radius (a half circle at most), click to finish")[len(self.pts)]

    def _arc(self):
        if len(self.pts) < 2:
            return None
        a, self.side = arc_from_ends(self.pts[0], self.pts[1], self.cur, self.side)
        return a

    def press(self, pt):
        self.cur = pt
        self.pts.append(pt)
        if len(self.pts) == 3:
            self.pts.pop()
            a = self._arc()
            if a is not None and a.r > 1e-6:
                a.style = self.scene.new_style()
                self.scene.add_entities([a], "Arc")
                self.scene.tool_done()
            else:
                self.pts = self.pts[:2]

    def cancel(self): self.pts = []; self.typed = ""

    def paint(self, p, vs):
        p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
        if len(self.pts) == 1:
            p.drawLine(QPointF(*self.pts[0]), QPointF(*self.cur))
        a = self._arc()
        if a is not None:
            span = (a.end - a.start) % 360 or 360
            pts = [QPointF(a.cx + a.r * math.cos(math.radians(a.start + span * i / 48)),
                           a.cy + a.r * math.sin(math.radians(a.start + span * i / 48))) for i in range(49)]
            p.drawPolyline(QPolygonF(pts))
            p.drawLine(QPointF(a.cx - 0.05, a.cy), QPointF(a.cx + 0.05, a.cy))
            p.drawLine(QPointF(a.cx, a.cy - 0.05), QPointF(a.cx, a.cy + 0.05))
            self.scene.draw_label(p, self.cur, f"R {a.r:.3f}", vs)


class BasePointTool(Tool):
    """After Copy / Cut: the base point (where the copy is held when pasting) is set
    automatically; click to choose another, or Enter / right-click / Esc keeps the automatic one."""
    name = "base"

    def hint(self):
        return "Base point: click to choose it, or press Enter / right-click to keep the automatic one (marked)"

    def press(self, pt):
        clipboard.CLIP["base"] = pt
        self.scene.say("Base point set. Ctrl+V to paste")
        self.scene.tool_done()

    def key(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.scene.tool_done(); return True
        return False

    def paint(self, p, vs):
        bx, by = clipboard.CLIP["base"]
        r = 8.0 / vs
        p.setPen(QPen(QColor(255, 0, 255), 0)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(bx, by), r, r)
        p.drawLine(QPointF(bx - r * 1.6, by), QPointF(bx + r * 1.6, by))
        p.drawLine(QPointF(bx, by - r * 1.6), QPointF(bx, by + r * 1.6))


class DotTool(Tool):
    """Solid dot: terminal / junction marker."""
    name = "dot"
    RADIUS = 0.04

    def hint(self): return "Dot: click to place a solid terminal/junction dot"

    def press(self, pt):
        self.scene.add_entities([m.Circle(pt[0], pt[1], self.RADIUS, self.scene.new_style(), filled=True)], "Dot")
        self.scene.tool_done()


class TextTool(Tool):
    name = "text"

    def hint(self): return "Text: click where the text goes"

    def press(self, pt):
        txt, ok = QInputDialog.getMultiLineText(QApplication.activeWindow(), "New text", "Text:")
        sc = self.scene
        if ok and txt.strip():
            ts = sc.current_text_style()
            sc.add_entities([m.Text(pt[0], pt[1], txt, txt, ts.height, 0.0, sc.new_style(ts.color),
                                    font=ts.font, align=ts.align, tstyle=ts.name)], "Text")
        sc.tool_done()


class SlotTool(Tool):
    """Mark where a wire lands on a part while drawing it (a `wire#` slot). Stays
    active for several slots; Esc / Enter / right-click finishes."""
    name = "slot"

    def hint(self):
        return "Slot: click each place a wire lands on the part (you name the terminal). Right-click / Esc finishes"

    def press(self, pt):
        sc = self.scene
        default = increment_number(sc.last_slot, 1) if sc.last_slot else "1"
        name, ok = QInputDialog.getText(QApplication.activeWindow(), "Wire# slot", "Terminal name:", text=default)
        if ok:
            name = name.strip()
            sc.last_slot = name
            sc.add_entities([m.SlotMark(pt[0], pt[1], name, m.Style("0"))], "Slot")


class OriginTool(Tool):
    """Pick the origin of the block being made: this point lands on the cursor when the
    block is placed."""
    name = "origin"

    def hint(self):
        return "Click the block's origin point (it sits on the cursor when the block is placed). Esc cancels"

    def press(self, pt):
        sc = self.scene
        pending, sc.pending_block = sc.pending_block, None
        sc.tool_done()
        if pending is not None:
            sc.finish_make_block(pending[0], pending[1], pt)

    def cancel(self):
        self.scene.pending_block = None
        self.typed = ""


class PlaceBlockTool(Tool):
    """Click to place the chosen library block. Ctrl+R rotates and Ctrl+M mirrors the
    ghost; wires running through the block's slots are trimmed to them."""
    name = "place"

    def __init__(self, scene):
        super().__init__(scene)
        self.block = scene.place_block_name
        self.rot = scene.place_rot
        self.mirror = False

    def hint(self):
        return f"Place {self.block}: click to drop. Ctrl+R rotates, Ctrl+M mirrors. Esc / right-click cancels"

    def rotate(self, deg):
        self.rot = (self.rot + deg) % 360
        self.scene.place_rot = self.rot

    def flip(self):
        self.mirror = not self.mirror

    def press(self, pt):
        sc = self.scene
        if self.block not in sc.project.blocks:
            sc.tool_done(); return
        ref = sc.place_block(self.block, pt, self.rot, self.mirror)
        sc.tool_done()
        sc._select_entities([ref])

    def paint(self, p, vs):
        blk = self.scene.project.blocks.get(self.block)
        if blk is None:
            return
        ref = m.BlockRef(self.block, self.cur[0], self.cur[1], self.rot, self.mirror)
        p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
        for e in bk.block_entities(blk, ref):
            draw_ghost(p, e, 0.0, 0.0)
        h = 0.04
        p.setPen(QPen(QColor("#ff8a1f"), 0))
        for _, (x, y) in bk.block_slots(blk, ref):
            p.drawEllipse(QPointF(x, y), h, h)


class EdgePicker:
    """Mixin: pick a line, or an edge of a rectangle. A rectangle is a single
    entity, so picking one of its edges 'explodes' it into four lines as part of
    the same undo step as the edit that follows (the rectangle is replaced)."""

    def _init_picker(self):
        self._virtual = {}        # rect id -> [4 Line] (cached so both picks share them)
        self._used = {}           # rect id -> rect actually picked from

    def _rect_lines(self, r):
        if r.id not in self._virtual:
            pts = [(r.x, r.y), (r.x + r.w, r.y), (r.x + r.w, r.y + r.h), (r.x, r.y + r.h)]
            lines = []
            for i in range(4):
                ln = m.Line(*pts[i], *pts[(i + 1) % 4], m.Style(**vars(r.style)))
                self.scene.tag_wire(ln)
                lines.append(ln)
            self._virtual[r.id] = lines
        return self._virtual[r.id]

    def pick_edge(self, pt, exclude=None):
        """-> (line, rect_or_None) nearest to pt within ~8 px, else (None, None)."""
        tol = 8.0 / self.scene.view_scale
        best, bd, brect = None, tol, None
        for e in self.scene.sheet.entities:
            if isinstance(e, m.Line):
                cands = [(e, None)]
            elif isinstance(e, m.Rect):
                cands = [(ln, e) for ln in self._rect_lines(e)]
            else:
                continue
            for ln, rect in cands:
                if ln is exclude:
                    continue
                d = dist_point_segment(pt, (ln.x1, ln.y1), (ln.x2, ln.y2))
                if d <= bd:
                    best, bd, brect = ln, d, rect
        if brect is not None:
            self._used[brect.id] = brect
        return best, brect

    def explosion(self):
        """-> (lines to add, rectangles to remove) for every rectangle picked from."""
        add, remove = [], []
        for rid, r in self._used.items():
            add += self._virtual[rid]
            remove.append(r)
        return add, remove

    def reset_picker(self):
        self._virtual, self._used = {}, {}


class MultilineTool(Tool):
    """Draw 2-4 parallel wires at once (e.g. L1 brown, L2 orange, L3 yellow, PE green).
    Click points along the path; Enter / Space / right-click finishes, Esc discards.
    Each wire goes on its own layer from the active preset; corners are mitred and
    the wires are recorded as one bundle."""
    name = "multiline"

    def __init__(self, scene):
        super().__init__(scene)
        self.points = []
        self.preset = scene.current_preset()

    @property
    def anchor(self): return self.points[-1] if self.points else None
    @anchor.setter
    def anchor(self, v): pass

    def _spacing(self):
        return self.preset.spacing or self.scene.sheet.row_pitch

    def hint(self):
        if self.preset is None:
            return "Multiline: no preset defined (Multiline presets...)"
        base = f"Multiline [{self.preset.name}: {' / '.join(self.preset.layers)}]"
        if not self.points:
            return base + ": click start point"
        return base + ": click next point, or type a length + Enter. Enter / right-click finishes, Esc cancels"

    def press(self, pt):
        if self.preset is None:
            self.scene.tool_done(); return
        if not self.points and not self.scene.ensure_preset_layers(self.preset):
            self.scene.tool_done(); return
        if not self.points or pt != self.points[-1]:
            self.points.append(pt)

    def commit_typed(self, v):
        if self.points and v > 0:
            self.points.append(point_on_line_at(self.points[-1], self.cur, v))

    def _path(self):
        pts = list(self.points)
        if pts:
            end = self.cur
            if self.typed:
                try:
                    end = point_on_line_at(pts[-1], self.cur, float(self.typed))
                except ValueError:
                    pass
            pts.append(end)
        return pts

    def finish(self):
        sc, n = self.scene, len(self.preset.layers) if self.preset else 0
        wires = multiline_wires(self.points, n, self._spacing()) if len(self.points) >= 2 else []
        self.points = []
        self.typed = ""
        if not wires:
            return
        lines = []
        existing = [e for e in sc.sheet.entities if isinstance(e, m.Line)]
        for layer, poly in zip(self.preset.layers, wires):
            poly = trim_wire_start(poly, layer, existing)       # L2 / L3 start at their own bus
            for a, b in zip(poly, poly[1:]):
                lines.append(m.Line(a[0], a[1], b[0], b[1], m.Style(layer=layer)))
        sc.undo.beginMacro("Multiline")
        sc.add_entities(lines, "Multiline")
        sc.undo.push(AddBundleCmd(sc.sheet, m.Bundle([ln.id for ln in lines], self.preset.name, self._spacing())))
        sc.undo.endMacro()

    def cancel(self): self.points = []; self.typed = ""

    def paint(self, p, vs):
        path = self._path()
        if len(path) < 2 or self.preset is None:
            return
        for layer, poly in zip(self.preset.layers, multiline_wires(path, len(self.preset.layers), self._spacing())):
            lay = self.scene.layers.get(layer)
            col = lay.color if lay else self.preset.colors[self.preset.layers.index(layer)]
            p.setPen(QPen(aci_color(col), 0, Qt.PenStyle.DashLine))
            for a, b in zip(poly, poly[1:]):
                p.drawLine(QLineF(a[0], a[1], b[0], b[1]))
        a, b = path[-2], path[-1]
        self.scene.draw_label(p, self.cur, f"{self.typed}_" if self.typed else f"{math.hypot(b[0]-a[0], b[1]-a[1]):.3f}", vs)


def draw_ghost(p, e, dx, dy):
    """Dashed outline of an entity shifted by (dx, dy) - the paste preview."""
    if isinstance(e, m.Group):
        for c in e.children:
            draw_ghost(p, c, dx, dy)
    elif isinstance(e, m.Line):
        p.drawLine(QLineF(e.x1 + dx, e.y1 + dy, e.x2 + dx, e.y2 + dy))
    elif isinstance(e, m.Rect):
        p.drawRect(QRectF(e.x + dx, e.y + dy, e.w, e.h))
    elif isinstance(e, m.Circle):
        p.drawEllipse(QPointF(e.cx + dx, e.cy + dy), e.r, e.r)
    elif isinstance(e, m.Arc):
        span = (e.end - e.start) % 360 or 360
        pts = []
        for i in range(25):
            a = math.radians(e.start + span * i / 24)
            pts.append((e.cx + dx + e.r * math.cos(a), e.cy + dy + e.r * math.sin(a)))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(QLineF(a[0], a[1], b[0], b[1]))
    elif isinstance(e, m.Text):
        x0, y0, x1, y1 = text_extent(e)
        p.drawRect(QRectF(x0 + dx, y0 + dy, x1 - x0, y1 - y0))
    elif isinstance(e, (m.BlockRef, m.SlotMark)):
        p.drawRect(QRectF(e.x + dx - 0.04, e.y + dy - 0.04, 0.08, 0.08))


class PasteTool(Tool):
    """Click to drop a copy of the clipboard (its lower-left corner lands on the click).
    Space / right-click afterwards repeats it."""
    name = "paste"

    def hint(self):
        n = len(clipboard.CLIP["items"])
        return f"Paste {n} object(s): click to place. Esc / right-click cancels"

    def press(self, pt):
        sc = self.scene
        if not clipboard.CLIP["items"]:
            sc.tool_done(); return
        clones = sc.paste_at(pt)
        sc.tool_done()
        sc._select_entities(clones)              # leave the pasted objects selected

    def paint(self, p, vs):
        base = clipboard.CLIP["base"]
        p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
        for e in clipboard.CLIP["items"]:
            draw_ghost(p, e, self.cur[0] - base[0], self.cur[1] - base[1])


class TrimTool(EdgePicker, Tool):
    """Click the part of a line to remove; it is cut back to the nearest crossing
    (any line, rectangle edge, circle or arc) on each side, or to the line's end.
    Rectangle edges can be trimmed too (the rectangle becomes four lines)."""
    name = "trim"

    def __init__(self, scene):
        super().__init__(scene)
        self._init_picker()

    def hint(self): return "Trim: click the part of a line or circle to remove (up to the crossings or its ends)"

    def press(self, pt):
        sc = self.scene
        self.reset_picker()
        e, rect = self.pick_edge(sc.raw)
        if e is None:
            tol = 8.0 / sc.view_scale
            def on_curve(c):
                if not isinstance(c, (m.Circle, m.Arc)) or getattr(c, "filled", False):
                    return False
                if abs(math.hypot(sc.raw[0] - c.cx, sc.raw[1] - c.cy) - c.r) > tol:
                    return False
                if isinstance(c, m.Arc):
                    span = (c.end - c.start) % 360 or 360
                    ang = math.degrees(math.atan2(sc.raw[1] - c.cy, sc.raw[0] - c.cx))
                    return (ang - c.start) % 360 <= span + math.degrees(tol / max(c.r, 1e-9))
                return True
            circ = next((c for c in sc.sheet.entities if on_curve(c)), None)
            if circ is None:
                sc.say("Trim: no line, circle or arc there - click on one"); return
            others = [x for x in sc.sheet.entities if x is not circ]
            if isinstance(circ, m.Arc):
                sc.undo.push(EditCmd(sc, "Trim arc", add=trim_arc(circ, sc.raw, others), remove=[circ]))
            else:
                arc = trim_circle(circ, sc.raw, others)
                if arc is None:
                    sc.say("Trim: the circle needs at least two crossings to cut between"); return
                sc.undo.push(EditCmd(sc, "Trim circle", add=[arc], remove=[circ]))
            sc.tool_done(); return
        cutters = [x for x in sc.sheet.entities if x is not e and x is not rect]
        segs = trim_line(e, sc.raw, cutters)
        add, remove = self.explosion()
        modify = []
        if not segs:
            if rect is None:
                remove.append(e)
            else:
                add.remove(e)
        else:
            (a, b) = segs[0]
            modify.append((e, {"x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1]}))
            if len(segs) == 2:
                (c, d) = segs[1]
                nl = m.Line(*c, *d, m.Style(**vars(e.style)))
                nl.number = m.WireNumber(e.number.mode, e.number.value) if e.number else None
                add.append(nl)
        sc.undo.push(EditCmd(sc, "Trim", modify=modify, add=add, remove=remove))
        sc.tool_done()


class _CornerTool(EdgePicker, Tool):
    """Pick two lines/rectangle edges (click on the side of each you want to KEEP)."""
    label = ""

    def __init__(self, scene):
        super().__init__(scene)
        self._init_picker()
        self.first = None          # (line, pick point, rect_or_None)

    def values_text(self): raise NotImplementedError
    def compute(self, l1, p1, l2, p2): raise NotImplementedError

    def hint(self):
        step = "click the first line" if self.first is None else "click the second line"
        return f"{self.label} {self.values_text()}: {step} (click the part to keep). Type a value + Enter/Space to change it"

    def _highlight(self, on):
        if self.first is None:
            return
        line, _, rect = self.first
        it = self.scene._items.get((rect or line).id)
        if it is not None:
            it.setSelected(on)

    def press(self, pt):
        sc = self.scene
        e, rect = self.pick_edge(sc.raw, exclude=self.first[0] if self.first else None)
        if e is None:
            sc.say(f"{self.label}: click on a line"); return
        if self.first is None:
            sc.clearSelection()
            self.first = (e, sc.raw, rect)
            self._highlight(True)
            return
        l1, p1, _ = self.first
        try:
            c1, c2, extra = self.compute(l1, p1, e, sc.raw)
        except ValueError as ex:
            sc.say(f"{self.label}: {ex}")
            self.cancel()
            return
        add, remove = self.explosion()
        if extra is not None:
            extra.style = m.Style(**vars(l1.style))
            sc.tag_wire(extra)
            add.append(extra)
        self._highlight(False)
        self.first = None
        sc.undo.push(EditCmd(sc, self.label, modify=[(l1, c1), (e, c2)], add=add, remove=remove))
        sc.clearSelection()
        sc.tool_done()

    def cancel(self):
        self._highlight(False)         # never leave the first pick highlighted
        self.first = None
        self.typed = ""
        self.reset_picker()


class FilletTool(_CornerTool):
    name = "fillet"
    label = "Fillet radius"
    def values_text(self): return f"{self.scene.fillet_radius:.3f}"
    def commit_typed(self, v): self.scene.fillet_radius = v
    def compute(self, l1, p1, l2, p2): return fillet_lines(l1, p1, l2, p2, self.scene.fillet_radius)


class ChamferTool(_CornerTool):
    """Two distances: d1 along the first line picked, d2 along the second.
    Type '0.25' for both the same, or '0.25,0.4' for different ones."""
    name = "chamfer"
    label = "Chamfer distances"
    def values_text(self): return f"{self.scene.chamfer_d1:.3f} / {self.scene.chamfer_d2:.3f}"

    def commit_values(self, vals):
        self.scene.chamfer_d1 = vals[0]
        self.scene.chamfer_d2 = vals[1] if len(vals) > 1 else vals[0]

    def compute(self, l1, p1, l2, p2):
        return chamfer_lines(l1, p1, l2, p2, self.scene.chamfer_d1, self.scene.chamfer_d2)


class ResizeTool(Tool):
    """Resize a group: four grips, one at the middle of each side. Dragging a grip
    moves that side perpendicular to itself (orthogonal); the neighbouring lines
    stretch to follow and corner arcs keep their radius. The group stays one
    group throughout. Esc / Enter / right-click / clicking away finishes."""
    name = "resize"

    def __init__(self, scene):
        super().__init__(scene)
        self.group = scene.resize_target
        self.drag = None
        self.hover = None

    def hint(self):
        if self.group is None:
            return "Resize: nothing to resize"
        return "Resize: drag a grip at the middle of a side. Esc / Enter / right-click / click away to finish"

    def _bbox(self):
        return bounds([self.group]) if self.group is not None else None

    def _grip_at(self, pt):
        bb = self._bbox()
        if bb is None:
            return None
        tol = 10.0 / self.scene.view_scale
        for side, (x, y) in grips_of(bb).items():
            if math.hypot(pt[0] - x, pt[1] - y) <= tol:
                return side
        return None

    def press(self, pt):
        raw = self.scene.raw
        side = self._grip_at(raw)
        if side is None:
            self.scene.tool_done(); return
        self.drag = {"side": side, "bbox": self._bbox(), "snap": snapshot([self.group]), "delta": 0.0}

    def move(self, pt):
        self.cur = pt
        raw = self.scene.raw
        if self.drag is None:
            self.hover = self._grip_at(raw)
            return
        d = self.drag
        side, bb = d["side"], d["bbox"]
        ss = self.scene.snap_settings
        g = snap_to_grid(raw, ss.grid_step, ss.origin) if ss.grid else raw
        horizontal = side in ("left", "right")
        coord = g[0] if horizontal else g[1]
        edge = {"left": bb[0], "right": bb[2], "bottom": bb[1], "top": bb[3]}[side]
        d["delta"] = clamp_delta(d["snap"], bb, side, coord - edge)
        stretch(d["snap"], bb, side, d["delta"])
        self.scene.sync_refresh(self.group)

    def release(self, pt):
        if self.drag is None:
            return
        d, self.drag = self.drag, None
        if abs(d["delta"]) > 1e-9:
            after = [(e, {k: getattr(e, k) for k in v}) for e, v in d["snap"]]
            self.scene.undo.push(StretchCmd(self.scene, self.group, d["snap"], after))

    def cancel(self):
        if self.drag is not None and self.group is not None:      # abandon a drag in progress
            restore(self.drag["snap"])
            self.scene.sync_refresh(self.group)
        self.drag = None
        self.scene.resize_target = None
        self.typed = ""

    def paint(self, p, vs):
        bb = self._bbox()
        if bb is None:
            return
        p.setPen(self._pen()); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(QPointF(bb[0], bb[1]), QPointF(bb[2], bb[3])))
        h = 5.0 / vs
        for side, (x, y) in grips_of(bb).items():
            active = side == self.hover or (self.drag is not None and self.drag["side"] == side)
            p.setPen(QPen(QColor("#0b1a2b"), 0))
            p.setBrush(QColor("#ffd400") if active else QColor("#4d9dff"))
            p.drawRect(QRectF(x - h, y - h, 2 * h, 2 * h))
        if self.drag is not None:
            self.scene.draw_label(p, self.cur, f"{bb[2]-bb[0]:.3f} x {bb[3]-bb[1]:.3f}", vs)


TOOLS = {"select": SelectTool, "line": LineTool, "rect": RectTool, "circle": CircleTool,
         "dot": DotTool, "text": TextTool, "trim": TrimTool, "fillet": FilletTool,
         "chamfer": ChamferTool, "multiline": MultilineTool, "paste": PasteTool, "resize": ResizeTool,
         "slot": SlotTool, "place": PlaceBlockTool, "origin": OriginTool,
         "arc": ArcTool, "base": BasePointTool}
