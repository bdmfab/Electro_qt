"""Wire crossings, hops, automatic junction dots and multiline auto-trim (Qt-free).

Rules (agreed with the user):
  * Two wires that cross are drawn with the more vertical one hopping over the other,
    unless a solid dot sits on the crossing (then they are connected).  Hops are only
    graphical - nothing is stored.
  * A wire end that lands on the side of another wire of the same layer is connected and
    gets an automatic dot (graphical), as does any point where three or more ends meet.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass
from . import model as m
from .numbering import _cross_point, _interior, _on_segment, TOL

HOP_R = 0.07          # hop radius (inches)
DOT_R = 0.04          # automatic dot radius = Dot tool radius


@dataclass
class Crossing:
    pt: tuple
    vert: m.Line       # the line that hops
    horiz: m.Line
    dot: object = None  # stored filled Circle on the crossing, if any

    @property
    def connected(self): return self.dot is not None


def wire_lines(project, sheet):
    out = []
    for e in sheet.entities:
        if isinstance(e, m.Line):
            lay = project.layers.get(e.style.layer)
            if lay is not None and lay.kind == "wire":
                out.append(e)
    return out


def _vertical_score(ln):
    return abs(ln.y2 - ln.y1) - abs(ln.x2 - ln.x1)


def crossings(lines, dots=()):
    """Interior-to-interior crossings of different lines, with any stored dot attached."""
    out = []
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            x = _cross_point(a, b)
            if x is None or not (_interior(x, a) and _interior(x, b)):
                continue
            v, h = (a, b) if _vertical_score(a) >= _vertical_score(b) else (b, a)
            dot = next((d for d in dots if math.hypot(d.cx - x[0], d.cy - x[1]) <= max(d.r, TOL) + TOL), None)
            out.append(Crossing(x, v, h, dot))
    return out


def sheet_crossings(project, sheet):
    dots = [e for e in sheet.entities if isinstance(e, m.Circle) and e.filled]
    return crossings(wire_lines(project, sheet), dots)


def hops(project, sheet):
    """Crossings that are drawn as hops: unconnected, and room for the arc on the vertical wire."""
    out = []
    for c in sheet_crossings(project, sheet):
        if c.connected:
            continue
        v = c.vert
        room = min(math.hypot(c.pt[0] - v.x1, c.pt[1] - v.y1), math.hypot(c.pt[0] - v.x2, c.pt[1] - v.y2))
        if room > HOP_R + TOL:
            out.append(c)
    return out


def junction_dots(lines):
    """Points that get an automatic dot: an end on the side of a same-layer line, or 3+ ends meeting."""
    pts = []

    def add(p):
        if not any(math.hypot(p[0] - q[0], p[1] - q[1]) <= TOL for q in pts):
            pts.append(p)

    ends = defaultdict(list)
    for ln in lines:
        for p in ((ln.x1, ln.y1), (ln.x2, ln.y2)):
            ends[(ln.style.layer, round(p[0], 4), round(p[1], 4))].append(ln)
            for o in lines:
                if o is not ln and o.style.layer == ln.style.layer and _interior(p, o):
                    add(p)
    for (layer, x, y), group in ends.items():
        if len(group) >= 3:
            add((x, y))
    return pts


def crossing_near(project, sheet, pt, tol):
    best, bd = None, tol
    for c in sheet_crossings(project, sheet):
        d = math.hypot(c.pt[0] - pt[0], c.pt[1] - pt[1])
        if d <= bd:
            best, bd = c, d
    return best


def trim_wire_start(poly, layer, existing):
    """Auto-trim for multiline: the wire's first segment starts at the first same-layer
    line that crosses it (L2 starts at the L2 bus, L3 at the L3 bus).  A wire that already
    starts on a same-layer line, or crosses none, is left alone."""
    if len(poly) < 2:
        return poly
    a, b = poly[0], poly[1]
    seg = m.Line(a[0], a[1], b[0], b[1])
    seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
    if seg_len < TOL:
        return poly
    same = [e for e in existing if isinstance(e, m.Line) and e.style.layer == layer]
    if any(_on_segment(a, e) for e in same):
        return poly
    best = None
    for e in same:
        d1 = ((b[0] - a[0]) * (e.y2 - e.y1) - (b[1] - a[1]) * (e.x2 - e.x1)) / seg_len
        if abs(d1) < 1e-9 or math.hypot(e.x2 - e.x1, e.y2 - e.y1) < TOL:
            continue
        x = _cross_point(seg, e)
        if x is None:
            continue
        t = math.hypot(x[0] - a[0], x[1] - a[1])
        if TOL < t < seg_len - TOL and (best is None or t < best[0]):
            best = (t, x)
    if best is None:
        return poly
    return [best[1]] + list(poly[1:])
