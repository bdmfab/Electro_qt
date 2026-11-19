"""Dots (the solid dots on the drawing: the automatic junction dots where wires tee together, and dots placed
with the Dot tool) and the wire numbers that reach them (Qt-free).

Used to label terminals: every wire number that ends at a dot is listed once with the number of dots it
reaches ("01131 (8)"), so a terminal block's terminals can be labelled from the drawing."""
from __future__ import annotations
import math
from collections import defaultdict
from . import model as m
from .junctions import wire_lines, junction_dots

REACH = 0.08            # a wire "ends at" a dot when it passes within this distance of the dot's centre


def _dist(px, py, ln):
    dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ln.x1) * dx + (py - ln.y1) * dy) / L2))
    return math.hypot(px - (ln.x1 + t * dx), py - (ln.y1 + t * dy))


def sheet_dots(project, sheet):
    """Every dot on a sheet: [(x, y, radius)]. Automatic junction dots plus dots placed with the Dot tool."""
    wires = wire_lines(project, sheet)
    pts = [(e.cx, e.cy, e.r) for e in sheet.entities if isinstance(e, m.Circle) and e.filled]
    for x, y in junction_dots(wires):
        if not any(math.hypot(x - px, y - py) <= 0.05 for px, py, _ in pts):
            pts.append((x, y, 0.04))
    return pts


def dot_numbers(project):
    """{wire number: [(page, x, y), ...]}: one entry per dot that a numbered wire reaches (a dot where two wires
    of the same number meet counts once). Dots with no numbered wire are left out."""
    out = defaultdict(list)
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        if sh.panel:
            continue
        wires = wire_lines(project, sh)
        for x, y, r in sheet_dots(project, sh):
            nums = {w.number.value for w in wires
                    if w.number is not None and w.number.value not in ("", "~") and _dist(x, y, w) <= max(REACH, r * 2)}
            for n in nums:
                out[n].append((pg, x, y))
    return dict(sorted(out.items()))


def used_counts(project, skip=None):
    """{wire number: how many terminals already carry it as their label}, over every panel layout
    (the object `skip` is left out - the dialog counts its own table)."""
    from . import panel as pn
    out = defaultdict(int)
    for sh in project.sheets.values():
        for o in pn.panel_objects(sh.entities):
            if o is skip or o.kind not in ("part", "terminals"):
                continue
            for lab in o.names.split("|") if o.names else []:
                if lab.strip():
                    out[lab.strip()] += 1
    return out
