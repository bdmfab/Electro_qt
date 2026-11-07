"""Snap engine (Qt-free). Grid, end, mid, center, quad; orthogonal constraint."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .geometry import snap_points, ortho


@dataclass
class SnapSettings:
    grid: bool = True
    grid_step: float = 0.05        # snap spacing
    origin: tuple = (0.0, 0.0)     # a grid point (row centre line on the sheet)
    ortho: bool = True
    end: bool = True
    mid: bool = True
    center: bool = True
    quad: bool = True
    # tangent: planned (needs the anchor point), not implemented yet


@dataclass
class SnapResult:
    point: tuple
    kind: str = ""        # "", grid, end, mid, center, quad


def snap_to_grid(pt, step, origin=(0.0, 0.0)):
    ox, oy = origin
    return ox + round((pt[0] - ox) / step) * step, oy + round((pt[1] - oy) / step) * step


def snap(pt, entities, s: SnapSettings, tol: float, anchor=None, extra=()) -> SnapResult:
    """tol is in model units (callers convert from pixels).

    With ortho on and an anchor, the point is first constrained to the dominant
    axis. Object snaps are then only accepted if they stay on that axis, so a
    wire can never be pulled off-axis by a nearby endpoint.
    """
    raw = pt
    constrained = bool(s.ortho and anchor is not None)
    if constrained:
        pt = ortho(anchor, pt)
    horizontal = constrained and abs(pt[1] - anchor[1]) < 1e-12 and \
        abs(raw[0] - anchor[0]) >= abs(raw[1] - anchor[1])

    best, best_d = None, tol
    enabled = {"end": s.end, "mid": s.mid, "center": s.center, "quad": s.quad}
    pts = [pair for e in entities for pair in snap_points(e)]
    pts += [("end", p) for p in extra]               # e.g. the slots of placed blocks
    for kind, p in pts:
        if not enabled.get(kind):
            continue
        if constrained:
            on_axis = abs(p[1] - anchor[1]) < 1e-9 if horizontal else abs(p[0] - anchor[0]) < 1e-9
            if not on_axis:
                continue
        d = math.hypot(p[0] - pt[0], p[1] - pt[1])
        if d <= best_d:
            best, best_d = SnapResult(p, kind), d
    if best:
        return best
    if s.grid:
        g = snap_to_grid(pt, s.grid_step, s.origin)
        if constrained:       # keep the fixed axis exactly on the anchor
            g = (g[0], anchor[1]) if horizontal else (anchor[0], g[1])
        return SnapResult(g, "grid")
    return SnapResult(pt, "")
