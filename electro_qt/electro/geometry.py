"""Qt-free geometry helpers: translate, snap points, bounds, ortho."""
from __future__ import annotations
import copy
import math
import re
from . import model as m


def walk(entities):
    """Every entity, including groups and everything inside them."""
    for e in entities:
        yield e
        if isinstance(e, m.Group):
            yield from walk(e.children)


def leaves(entities):
    """Every non-group entity, looking inside groups."""
    for e in entities:
        if isinstance(e, m.Group):
            yield from leaves(e.children)
        else:
            yield e


def translate(e, dx: float, dy: float) -> None:
    if isinstance(e, m.Group):
        for c in e.children:
            translate(c, dx, dy)
    elif isinstance(e, m.Line):
        e.x1 += dx; e.x2 += dx; e.y1 += dy; e.y2 += dy
    elif isinstance(e, m.Rect):
        e.x += dx; e.y += dy
    elif isinstance(e, (m.Circle, m.Arc)):
        e.cx += dx; e.cy += dy
    elif isinstance(e, (m.Text, m.BlockRef, m.SlotMark)):
        e.x += dx; e.y += dy


def arc_point(a: m.Arc, deg: float):
    r = math.radians(deg)
    return a.cx + a.r * math.cos(r), a.cy + a.r * math.sin(r)


def snap_points(e):
    """[(kind, (x, y))] with kind in end/mid/center/quad."""
    out = []
    if isinstance(e, m.Group):
        for c in e.children:
            out += snap_points(c)
    elif isinstance(e, m.Line):
        out += [("end", (e.x1, e.y1)), ("end", (e.x2, e.y2)),
                ("mid", ((e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2))]
    elif isinstance(e, m.Rect):
        x0, y0, x1, y1 = e.x, e.y, e.x + e.w, e.y + e.h
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        out += [("end", p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        out += [("mid", p) for p in ((xm, y0), (x1, ym), (xm, y1), (x0, ym))]
        out.append(("center", (xm, ym)))
    elif isinstance(e, m.Circle):
        out.append(("center", (e.cx, e.cy)))
        out += [("quad", (e.cx + dx * e.r, e.cy + dy * e.r))
                for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))]
    elif isinstance(e, m.Arc):
        out.append(("center", (e.cx, e.cy)))
        out += [("end", arc_point(e, e.start)), ("end", arc_point(e, e.end))]
        span = (e.end - e.start) % 360
        out.append(("mid", arc_point(e, e.start + span / 2)))
        for q in (0, 90, 180, 270):
            if (q - e.start) % 360 <= span:
                out.append(("quad", arc_point(e, q)))
    elif isinstance(e, (m.Text, m.BlockRef, m.SlotMark)):
        out.append(("end", (e.x, e.y)))
    return out


def text_extent(t: m.Text):
    """Approximate box of a text object (the real glyph metrics live in Qt, so
    this estimates: ~0.7 x height per character, 1.6 x height per line)."""
    lines = ("" if getattr(t, "hidden", False) else (t.resolved or t.source)).split("\n")
    w = max((len(s) for s in lines), default=1) * 0.7 * t.height
    h = t.height
    x0, y1 = t.x, t.y + h
    y0 = t.y - (len(lines) - 1) * 1.6 * h - 0.25 * h
    if t.rotation % 360:
        c, s = math.cos(math.radians(t.rotation)), math.sin(math.radians(t.rotation))
        pts = [(t.x + (px - t.x) * c - (py - t.y) * s, t.y + (px - t.x) * s + (py - t.y) * c)
               for px, py in ((x0, y0), (x0 + w, y0), (x0 + w, y1), (x0, y1))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    return x0, y0, x0 + w, y1


def arc_extent_points(a: m.Arc):
    """End points plus any quadrant points inside the sweep (true extent of an arc)."""
    span = (a.end - a.start) % 360 or 360
    pts = [arc_point(a, a.start), arc_point(a, a.end)]
    for q in (0, 90, 180, 270):
        if (q - a.start) % 360 <= span:
            pts.append(arc_point(a, q))
    return pts


def ref_bounds(ref, blk, blocks=None):
    """World bounds of one placed block (its graphics and slots, rotated / mirrored / moved)."""
    local = bounds(blk.entities, blocks)
    pts = [(s.x, s.y) for s in blk.slots]
    if local:
        pts += [(local[0], local[1]), (local[2], local[1]), (local[2], local[3]), (local[0], local[3])]
    if not pts:
        return (ref.x, ref.y, ref.x, ref.y)
    r = math.radians(ref.rotation); c, sn = math.cos(r), math.sin(r)
    world = []
    for x, y in pts:
        if ref.mirror:
            x = -x
        world.append((ref.x + x * c - y * sn, ref.y + x * sn + y * c))
    xs, ys = [w[0] for w in world], [w[1] for w in world]
    return min(xs), min(ys), max(xs), max(ys)


def bounds(entities, blocks=None):
    """(xmin, ymin, xmax, ymax) or None. Looks inside groups. With `blocks` (name -> BlockDef)
    a placed block counts with its real extent instead of just its origin."""
    xs, ys = [], []
    for e in leaves(entities):
        if isinstance(e, m.BlockRef) and blocks and e.block in blocks:
            b = ref_bounds(e, blocks[e.block], blocks)
            xs += [b[0], b[2]]; ys += [b[1], b[3]]
        elif isinstance(e, m.Text):
            x0, y0, x1, y1 = text_extent(e)
            xs += [x0, x1]; ys += [y0, y1]
        elif isinstance(e, m.Rect):
            xs += [e.x, e.x + e.w]; ys += [e.y, e.y + e.h]
        elif isinstance(e, m.Circle):
            xs += [e.cx - e.r, e.cx + e.r]; ys += [e.cy - e.r, e.cy + e.r]
        elif isinstance(e, m.Arc):
            for x, y in arc_extent_points(e):
                xs.append(x); ys.append(y)
        else:
            for _, (x, y) in snap_points(e):
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def ortho(anchor, pt):
    """Constrain pt to the dominant axis from anchor."""
    dx, dy = pt[0] - anchor[0], pt[1] - anchor[1]
    return (pt[0], anchor[1]) if abs(dx) >= abs(dy) else (anchor[0], pt[1])


def point_on_line_at(anchor, toward, length):
    """Point `length` from anchor in the direction of `toward`."""
    dx, dy = toward[0] - anchor[0], toward[1] - anchor[1]
    d = math.hypot(dx, dy)
    if d == 0:
        return anchor
    return anchor[0] + dx / d * length, anchor[1] + dy / d * length


# ------------------------------------------------------------ trim / fillet
_EPS = 1e-9


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _unit(v):
    d = math.hypot(*v)
    return (v[0] / d, v[1] / d)


def _cutter_segments(c):
    if isinstance(c, m.Line):
        yield (c.x1, c.y1), (c.x2, c.y2)
    elif isinstance(c, m.Rect):
        x0, y0, x1, y1 = c.x, c.y, c.x + c.w, c.y + c.h
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for i in range(4):
            yield pts[i], pts[(i + 1) % 4]


def cut_params(line: m.Line, cutters) -> list:
    """Parameters t in (0,1) where `line` is crossed or touched by cutters."""
    p = (line.x1, line.y1)
    r = (line.x2 - line.x1, line.y2 - line.y1)
    ts = []
    for c in leaves(cutters):
        for a, b in _cutter_segments(c):
            s = _sub(b, a)
            rxs = _cross(r, s)
            if abs(rxs) < _EPS:
                continue
            qp = _sub(a, p)
            t, u = _cross(qp, s) / rxs, _cross(qp, r) / rxs
            if -_EPS <= u <= 1 + _EPS:
                ts.append(t)
        if isinstance(c, (m.Circle, m.Arc)):
            f = _sub(p, (c.cx, c.cy))
            A, B, C = _dot(r, r), 2 * _dot(f, r), _dot(f, f) - c.r ** 2
            disc = B * B - 4 * A * C
            if A > 0 and disc >= 0:
                sq = math.sqrt(disc)
                for t in ((-B - sq) / (2 * A), (-B + sq) / (2 * A)):
                    x, y = p[0] + t * r[0], p[1] + t * r[1]
                    if isinstance(c, m.Arc):
                        ang = math.degrees(math.atan2(y - c.cy, x - c.cx))
                        if (ang - c.start) % 360 > (c.end - c.start) % 360 + 1e-7:
                            continue
                    ts.append(t)
    out = []
    for t in sorted(ts):
        if _EPS < t < 1 - _EPS and (not out or t - out[-1] > 1e-9):
            out.append(t)
    return out


def trim_line(line: m.Line, click, cutters) -> list:
    """Remove the portion of `line` under `click`, bounded by the nearest
    crossings (or the line's ends). Returns the remaining segments
    [((x1,y1),(x2,y2)), ...] (0, 1 or 2 of them)."""
    p = (line.x1, line.y1)
    r = (line.x2 - line.x1, line.y2 - line.y1)
    rr = _dot(r, r)
    tc = 0.0 if rr == 0 else max(0.0, min(1.0, _dot(_sub(click, p), r) / rr))
    ts = [0.0] + cut_params(line, cutters) + [1.0]
    a, b = 0.0, 1.0
    for lo, hi in zip(ts, ts[1:]):
        if lo <= tc <= hi:
            a, b = lo, hi
            break

    def at(t):
        return p[0] + t * r[0], p[1] + t * r[1]
    out = []
    if a > _EPS:
        out.append((p, at(a)))
    if b < 1 - _EPS:
        out.append((at(b), (line.x2, line.y2)))
    return out


def circle_cut_angles(circ, cutters) -> list:
    """Angles (degrees, 0-360, sorted, de-duplicated) where the circle meets the cutters."""
    cx, cy, R = circ.cx, circ.cy, circ.r
    angs = []

    def add(x, y):
        angs.append(math.degrees(math.atan2(y - cy, x - cx)) % 360)

    for c in leaves(cutters):
        if c is circ:
            continue
        for a, b in _cutter_segments(c):
            d = _sub(b, a); f = _sub(a, (cx, cy))
            A, B, C = _dot(d, d), 2 * _dot(f, d), _dot(f, f) - R * R
            disc = B * B - 4 * A * C
            if A <= 0 or disc < 0:
                continue
            sq = math.sqrt(disc)
            for t in ((-B - sq) / (2 * A), (-B + sq) / (2 * A)):
                if -_EPS <= t <= 1 + _EPS:
                    add(a[0] + t * d[0], a[1] + t * d[1])
        if isinstance(c, (m.Circle, m.Arc)):
            dx, dy = c.cx - cx, c.cy - cy
            dd = math.hypot(dx, dy)
            if dd < _EPS or dd > R + c.r or dd < abs(R - c.r):
                continue
            a_ = (R * R - c.r * c.r + dd * dd) / (2 * dd)
            h2 = R * R - a_ * a_
            if h2 < 0:
                continue
            h = math.sqrt(h2)
            mx, my = cx + a_ * dx / dd, cy + a_ * dy / dd
            for sgn in (1, -1):
                x, y = mx + sgn * h * dy / dd, my - sgn * h * dx / dd
                if isinstance(c, m.Arc):
                    ang = math.degrees(math.atan2(y - c.cy, x - c.cx))
                    if (ang - c.start) % 360 > (c.end - c.start) % 360 + 1e-7:
                        continue
                add(x, y)
    out = []
    for a in sorted(angs):
        if not out or a - out[-1] > 1e-6:
            out.append(a)
    if len(out) > 1 and out[0] + 360 - out[-1] <= 1e-6:
        out.pop()
    return out


def trim_circle(circ: m.Circle, click, cutters):
    """Cut the part of the circle under `click` out, between the nearest crossings on each
    side. Returns the remaining m.Arc, or None when fewer than two crossings exist."""
    angs = circle_cut_angles(circ, cutters)
    if len(angs) < 2:
        return None
    ac = math.degrees(math.atan2(click[1] - circ.cy, click[0] - circ.cx)) % 360
    hi = next((a for a in angs if a > ac), angs[0])               # next crossing counter-clockwise
    lo = next((a for a in reversed(angs) if a < ac), angs[-1])    # next crossing clockwise
    return m.Arc(circ.cx, circ.cy, circ.r, hi, lo, m.Style(**vars(circ.style)))


def trim_arc(arc: m.Arc, click, cutters) -> list:
    """Cut the part of the arc under `click` out, up to the nearest crossings (or the arc's
    ends). Returns the remaining m.Arc pieces (0, 1 or 2)."""
    span = (arc.end - arc.start) % 360 or 360.0
    ts = [0.0]
    for a in circle_cut_angles(arc, cutters):
        u = (a - arc.start) % 360
        if _EPS < u < span - _EPS:
            ts.append(u)
    ts = sorted(ts) + [span]
    uc = (math.degrees(math.atan2(click[1] - arc.cy, click[0] - arc.cx)) - arc.start) % 360
    uc = min(uc, span)
    lo, hi = 0.0, span
    for a, b in zip(ts, ts[1:]):
        if a <= uc <= b:
            lo, hi = a, b
            break
    out = []
    if lo > 1e-6:
        out.append(m.Arc(arc.cx, arc.cy, arc.r, arc.start, arc.start + lo, m.Style(**vars(arc.style))))
    if hi < span - 1e-6:
        out.append(m.Arc(arc.cx, arc.cy, arc.r, arc.start + hi, arc.start + span, m.Style(**vars(arc.style))))
    return out


def arc_from_ends(p1, p2, c, side=1):
    """Arc through the chord p1-p2 whose centre is the projection of `c` on the chord's
    perpendicular bisector (so it never goes past a half circle; the arc bulges away from the
    centre). -> (Arc or None, side used)."""
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(vx, vy)
    if L < 1e-9:
        return None, side
    ux, uy = vx / L, vy / L
    nx, ny = -uy, ux
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    d = (c[0] - mx) * nx + (c[1] - my) * ny
    if abs(d) < 1e-9:
        d = 0.0
    else:
        side = -1 if d > 0 else 1
    cx, cy = mx + d * nx, my + d * ny
    R = math.hypot(L / 2, d)
    a1 = math.degrees(math.atan2(p1[1] - cy, p1[0] - cx)) % 360
    a2 = math.degrees(math.atan2(p2[1] - cy, p2[0] - cx)) % 360
    for s_, e_ in ((a1, a2), (a2, a1)):
        mid = math.radians(s_ + ((e_ - s_) % 360) / 2)
        px, py = cx + R * math.cos(mid), cy + R * math.sin(mid)
        if (vx * (py - p1[1]) - vy * (px - p1[0])) * side > 0:
            return m.Arc(cx, cy, R, s_, e_), side
    return None, side


def _corner(l1, pick1, l2, pick2):
    """Shared set-up for fillet/chamfer. Returns P, (u1,far1,len1,far1_is_end2), (...)."""
    p1, d1 = (l1.x1, l1.y1), (l1.x2 - l1.x1, l1.y2 - l1.y1)
    p2, d2 = (l2.x1, l2.y1), (l2.x2 - l2.x1, l2.y2 - l2.y1)
    den = _cross(d1, d2)
    if abs(den) < _EPS:
        raise ValueError("Lines are parallel")
    t = _cross(_sub(p2, p1), d2) / den
    P = (p1[0] + t * d1[0], p1[1] + t * d1[1])

    def side(line, pick):
        a, b = (line.x1, line.y1), (line.x2, line.y2)
        d = _unit(_sub(b, a))
        s = _dot(_sub(pick, P), d)
        if abs(s) < _EPS:                       # pick sits on the corner: use longer side
            s = max(_dot(_sub(a, P), d), _dot(_sub(b, P), d), key=abs)
        u = d if s >= 0 else (-d[0], -d[1])
        da, db = _dot(_sub(a, P), u), _dot(_sub(b, P), u)
        far_is_end2 = db >= da
        return u, (db if far_is_end2 else da), far_is_end2

    return P, side(l1, pick1), side(l2, pick2)


def _new_coords(line, far_is_end2, T):
    """Replace the endpoint nearest the corner (the one that is not `far`)."""
    return ({"x1": T[0], "y1": T[1]} if far_is_end2 else {"x2": T[0], "y2": T[1]})


def fillet_lines(l1, pick1, l2, pick2, radius):
    """-> (coords1, coords2, arc_or_None). coords are attribute dicts to apply.
    radius 0 just makes a sharp corner (trim/extend both lines to meet)."""
    P, (u1, len1, e1), (u2, len2, e2) = _corner(l1, pick1, l2, pick2)
    if len1 <= _EPS or len2 <= _EPS:
        raise ValueError("Corner is beyond the far end of a line")
    cosang = max(-1.0, min(1.0, _dot(u1, u2)))
    theta = math.acos(cosang)
    if theta < 1e-6 or abs(theta - math.pi) < 1e-6:
        raise ValueError("Lines are parallel")
    if radius <= 0:
        return _new_coords(l1, e1, P), _new_coords(l2, e2, P), None
    d = radius / math.tan(theta / 2)
    if d >= len1 - _EPS or d >= len2 - _EPS:
        raise ValueError("Radius too large for these lines")
    T1 = (P[0] + u1[0] * d, P[1] + u1[1] * d)
    T2 = (P[0] + u2[0] * d, P[1] + u2[1] * d)
    bis = _unit((u1[0] + u2[0], u1[1] + u2[1]))
    k = radius / math.sin(theta / 2)
    C = (P[0] + bis[0] * k, P[1] + bis[1] * k)
    a1 = math.degrees(math.atan2(T1[1] - C[1], T1[0] - C[0])) % 360
    a2 = math.degrees(math.atan2(T2[1] - C[1], T2[0] - C[0])) % 360
    start, end = (a1, a2) if (a2 - a1) % 360 <= 180 else (a2, a1)
    arc = m.Arc(C[0], C[1], radius, start, end)
    return _new_coords(l1, e1, T1), _new_coords(l2, e2, T2), arc


def chamfer_lines(l1, pick1, l2, pick2, d1, d2=None):
    """-> (coords1, coords2, new_line). Chamfer d1 along the first line and
    d2 along the second (d2 defaults to d1)."""
    d2 = d1 if d2 is None else d2
    P, (u1, len1, e1), (u2, len2, e2) = _corner(l1, pick1, l2, pick2)
    if d1 <= 0 or d2 <= 0:
        return _new_coords(l1, e1, P), _new_coords(l2, e2, P), None
    if d1 >= len1 - _EPS or d2 >= len2 - _EPS:
        raise ValueError("Distance too large for these lines")
    T1 = (P[0] + u1[0] * d1, P[1] + u1[1] * d1)
    T2 = (P[0] + u2[0] * d2, P[1] + u2[1] * d2)
    return _new_coords(l1, e1, T1), _new_coords(l2, e2, T2), m.Line(*T1, *T2)


def dist_point_segment(pt, a, b):
    ab = _sub(b, a)
    L2 = _dot(ab, ab)
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, _dot(_sub(pt, a), ab) / L2))
    c = (a[0] + t * ab[0], a[1] + t * ab[1])
    return math.hypot(pt[0] - c[0], pt[1] - c[1])


# ------------------------------------------------------------ group resize
_STRETCH_FIELDS = {m.Line: ("x1", "y1", "x2", "y2"), m.Circle: ("cx", "cy"),
                   m.Arc: ("cx", "cy", "start", "end"), m.Rect: ("x", "y", "w", "h"),
                   m.Text: ("x", "y", "rotation"), m.BlockRef: ("x", "y", "rotation", "mirror"),
                   m.SlotMark: ("x", "y")}


def snapshot(entities):
    """[(entity, {field: value})] for every leaf, so an edit can be replayed or undone."""
    out = []
    for e in leaves(entities):
        keys = _STRETCH_FIELDS.get(type(e))
        if keys:
            out.append((e, {k: getattr(e, k) for k in keys}))
    return out


def restore(snap):
    for e, vals in snap:
        for k, v in vals.items():
            setattr(e, k, v)


def grips_of(bbox):
    """Mid-point of each side of a bounding box."""
    x0, y0, x1, y1 = bbox
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return {"left": (x0, ym), "right": (x1, ym), "bottom": (xm, y0), "top": (xm, y1)}


def clamp_delta(snap, bbox, side, delta, minimum=0.1):
    """Keep the dragged edge from crossing the opposite one (corner arcs need
    at least two radii)."""
    x0, y0, x1, y1 = bbox
    extent = (x1 - x0) if side in ("left", "right") else (y1 - y0)
    radii = [e.r for e, _ in snap if isinstance(e, m.Arc)]
    least = max(minimum, 2 * max(radii)) if radii else minimum
    if side in ("right", "top"):
        return max(delta, least - extent)
    return min(delta, extent - least)


def stretch(snap, bbox, side, delta):
    """Move one side of a group by `delta` (perpendicular to that side).

    Everything on the dragged side of the centre line moves; lines that span the
    centre are lengthened or shortened. Corner arcs travel with their edge, so a
    rounded rectangle keeps its radii. Always computed from the snapshot values,
    so repeated calls while dragging never drift."""
    restore(snap)
    x0, y0, x1, y1 = bbox
    horizontal = side in ("left", "right")          # edge moves along x
    mid = (x0 + x1) / 2 if horizontal else (y0 + y1) / 2
    positive = side in ("right", "top")

    def moves(v):
        return v > mid if positive else v < mid

    for e, v in snap:
        if isinstance(e, m.Line):
            names = ("x1", "x2") if horizontal else ("y1", "y2")
        elif isinstance(e, (m.Circle, m.Arc, m.Text, m.BlockRef, m.SlotMark)):
            names = ("cx",) if horizontal and hasattr(e, "cx") else ("cy",) if hasattr(e, "cy") else \
                    ("x",) if horizontal else ("y",)
        elif isinstance(e, m.Rect):
            lo, ext = ("x", "w") if horizontal else ("y", "h")
            a, b = v[lo], v[lo] + v[ext]
            a2 = a + delta if moves(a) else a
            b2 = b + delta if moves(b) else b
            setattr(e, lo, a2); setattr(e, ext, b2 - a2)
            continue
        else:
            continue
        for n in names:
            if moves(v[n]):
                setattr(e, n, v[n] + delta)


# ------------------------------------------------------------ multiline wires
def _dedupe(points):
    out = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(tuple(p))
    return out


def offset_polyline(points, off):
    """Offset a polyline to the left of travel by `off` (negative = right),
    with mitred corners."""
    pts = _dedupe(points)
    if len(pts) < 2:
        return []
    segs = []
    for a, b in zip(pts, pts[1:]):
        d = _unit(_sub(b, a))
        segs.append((d, (-d[1], d[0])))
    out = [(pts[0][0] + segs[0][1][0] * off, pts[0][1] + segs[0][1][1] * off)]
    for i in range(1, len(pts) - 1):
        (d1, n1), (d2, n2) = segs[i - 1], segs[i]
        p = (pts[i][0] + n1[0] * off, pts[i][1] + n1[1] * off)
        q = (pts[i][0] + n2[0] * off, pts[i][1] + n2[1] * off)
        den = _cross(d1, d2)
        if abs(den) < 1e-9:
            out.append(q)
        else:
            s = _cross(_sub(q, p), d2) / den
            out.append((p[0] + s * d1[0], p[1] + s * d1[1]))
    n = segs[-1][1]
    out.append((pts[-1][0] + n[0] * off, pts[-1][1] + n[1] * off))
    return out


def multiline_wires(points, count, spacing):
    """`count` parallel polylines centred on the path. Wire 0 is the top one on a
    horizontal run, the left one on a vertical run (decided by the first segment)."""
    pts = _dedupe(points)
    if len(pts) < 2 or count < 1:
        return []
    d = _unit(_sub(pts[1], pts[0]))
    n = (-d[1], d[0])
    toward = (0.0, 1.0) if abs(d[0]) >= abs(d[1]) else (-1.0, 0.0)
    sigma = -1.0 if _dot(n, toward) > 0 else 1.0
    return [offset_polyline(pts, sigma * (k - (count - 1) / 2) * spacing) for k in range(count)]


# ------------------------------------------------------------ align / distribute
ALIGN_MODES = ("left", "right", "top", "bottom", "hcenter", "vcenter", "dist_h", "dist_v")


def align_moves(items, mode):
    """items = [(key, (x0, y0, x1, y1))] -> [(key, dx, dy)].
    left/right/top/bottom line up on the outermost edge of the selection;
    hcenter/vcenter line up on the middle of the selection's box;
    dist_h/dist_v space three or more items with equal gaps (outer two stay put)."""
    if mode not in ALIGN_MODES:
        raise ValueError(mode)
    if not items:
        return []
    X0 = min(b[0] for _, b in items); Y0 = min(b[1] for _, b in items)
    X1 = max(b[2] for _, b in items); Y1 = max(b[3] for _, b in items)
    out = []
    if mode in ("dist_h", "dist_v"):
        if len(items) < 3:
            return [(k, 0.0, 0.0) for k, _ in items]
        i0, i1 = (0, 2) if mode == "dist_h" else (1, 3)
        order = sorted(items, key=lambda kb: kb[1][i0])
        total = (X1 - X0) if mode == "dist_h" else (Y1 - Y0)
        sizes = [b[i1] - b[i0] for _, b in order]
        gap = (total - sum(sizes)) / (len(order) - 1)
        pos = (X0 if mode == "dist_h" else Y0)
        for (k, b), size in zip(order, sizes):
            d = pos - b[i0]
            out.append((k, d, 0.0) if mode == "dist_h" else (k, 0.0, d))
            pos += size + gap
        return out
    for k, (x0, y0, x1, y1) in items:
        dx = dy = 0.0
        if mode == "left": dx = X0 - x0
        elif mode == "right": dx = X1 - x1
        elif mode == "bottom": dy = Y0 - y0
        elif mode == "top": dy = Y1 - y1
        elif mode == "hcenter": dx = (X0 + X1) / 2 - (x0 + x1) / 2
        elif mode == "vcenter": dy = (Y0 + Y1) / 2 - (y0 + y1) / 2
        out.append((k, dx, dy))
    return out


# ------------------------------------------------------------ copy / rotate / mirror
def clone_entity(e):
    """Deep copy with fresh ids (groups too). Copied wires start unnumbered (auto)
    so a pasted wire never carries a duplicate override."""
    c = copy.deepcopy(e)
    for x in walk([c]):
        x.id = m.new_id()
        if isinstance(x, m.Line):
            x.mark = ""                      # a copy is never a second numbering origin
            if x.number is not None:
                x.number = m.WireNumber("auto", "")
    return c


def _rot(p, c, deg):
    r = math.radians(deg)
    cs, sn = math.cos(r), math.sin(r)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return c[0] + dx * cs - dy * sn, c[1] + dx * sn + dy * cs


def rotate_entity(e, pivot, deg):
    """Rotate in place about pivot (degrees, counter-clockwise).
    A Rect can only turn in 90 degree steps (raises ValueError otherwise)."""
    if isinstance(e, m.Group):
        for c in e.children:
            rotate_entity(c, pivot, deg)
    elif isinstance(e, m.Line):
        e.x1, e.y1 = _rot((e.x1, e.y1), pivot, deg)
        e.x2, e.y2 = _rot((e.x2, e.y2), pivot, deg)
    elif isinstance(e, m.Rect):
        if abs(deg / 90 - round(deg / 90)) > 1e-9:
            raise ValueError("A rectangle can only be rotated in 90 degree steps "
                             "(explode it into lines first for other angles)")
        pts = [_rot(p, pivot, deg) for p in ((e.x, e.y), (e.x + e.w, e.y + e.h))]
        e.x, e.y = min(p[0] for p in pts), min(p[1] for p in pts)
        e.w, e.h = abs(pts[1][0] - pts[0][0]), abs(pts[1][1] - pts[0][1])
    elif isinstance(e, m.Circle):
        e.cx, e.cy = _rot((e.cx, e.cy), pivot, deg)
    elif isinstance(e, m.Arc):
        e.cx, e.cy = _rot((e.cx, e.cy), pivot, deg)
        e.start, e.end = (e.start + deg) % 360, (e.end + deg) % 360
    elif isinstance(e, (m.Text, m.BlockRef, m.SlotMark)):
        e.x, e.y = _rot((e.x, e.y), pivot, deg)
        e.rotation = (e.rotation + deg) % 360


def mirror_entity(e, axis, c):
    """Mirror in place. axis 'v': flip left-right about the vertical line x = c;
    axis 'h': flip top-bottom about the horizontal line y = c. Text keeps reading
    the right way round (only its anchor moves)."""
    vert = axis == "v"
    if isinstance(e, m.Group):
        for ch in e.children:
            mirror_entity(ch, axis, c)
    elif isinstance(e, m.Line):
        if vert:
            e.x1, e.x2 = 2 * c - e.x1, 2 * c - e.x2
        else:
            e.y1, e.y2 = 2 * c - e.y1, 2 * c - e.y2
    elif isinstance(e, m.Rect):
        if vert:
            e.x = 2 * c - (e.x + e.w)
        else:
            e.y = 2 * c - (e.y + e.h)
    elif isinstance(e, m.Circle):
        if vert:
            e.cx = 2 * c - e.cx
        else:
            e.cy = 2 * c - e.cy
    elif isinstance(e, m.Arc):
        if vert:
            e.cx = 2 * c - e.cx
            e.start, e.end = (180 - e.end) % 360, (180 - e.start) % 360
        else:
            e.cy = 2 * c - e.cy
            e.start, e.end = (-e.end) % 360, (-e.start) % 360
    elif isinstance(e, (m.Text, m.BlockRef, m.SlotMark)):
        if vert:
            e.x = 2 * c - e.x
        else:
            e.y = 2 * c - e.y
        if isinstance(e, m.BlockRef):
            e.mirror = not e.mirror
            if not vert:
                e.rotation = (e.rotation + 180) % 360


# ---------------------------------------------------------------- arrays
_DIGITS = re.compile(r"(\d+)(?!.*\d)")


def increment_number(s: str, n: int) -> str:
    """Add n to the LAST run of digits in s, keeping zero padding ('TB09' + 1 -> 'TB10').
    Text without digits (or with a {field} code) is returned unchanged."""
    if "{" in s:
        return s
    mt = _DIGITS.search(s)
    if not mt:
        return s
    digits = mt.group(1)
    val = max(0, int(digits) + n)
    new = str(val).zfill(len(digits)) if digits.startswith("0") else str(val)
    return s[:mt.start(1)] + new + s[mt.end(1):]


def _bump_texts(clone, n, step):
    for x in walk([clone]):
        if isinstance(x, m.Text) and "{" not in x.source:
            x.source = increment_number(x.source, n * step)
            x.resolved = x.source


def array_linear(entities, rows, cols, dx, dy, increment=False, step=1):
    """Copies of `entities` on a rows x cols grid (the original is cell 0,0 and is
    not repeated). Copy k = r*cols + c counts upward; text numbers grow by `step` per copy."""
    out = []
    for r in range(rows):
        for c in range(cols):
            k = r * cols + c
            if k == 0:
                continue
            group = []
            for e in entities:
                cl = clone_entity(e)
                translate(cl, c * dx, r * dy)
                if increment:
                    _bump_texts(cl, k, step)
                group.append(cl)
            out.extend(group)
    return out


def array_polar(entities, count, total_angle, center, rotate_items=True, increment=False, step=1, blocks=None):
    """count items spread over total_angle degrees around center (the original is
    item 0). A full circle (360) spaces them evenly with no overlap at the end."""
    out = []
    if count < 2:
        return out
    n_steps = count if abs(total_angle) >= 360 else count - 1
    inc = total_angle / n_steps
    b = bounds(entities, blocks)
    c0 = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    for k in range(1, count):
        ang = inc * k
        for e in entities:
            cl = clone_entity(e)
            if rotate_items:
                rotate_entity(cl, center, ang)
            else:
                p = _rot(c0, center, ang)
                translate(cl, p[0] - c0[0], p[1] - c0[1])
            if increment:
                _bump_texts(cl, k, step)
            out.append(cl)
    return out


# ---------------------------------------------------------------- grips on lines / circles
def _nk(x, y):
    return (round(x, 5), round(y, 5))


def line_nodes(lines):
    """{point: [(line, 1|2)]} for every line end (points that coincide share a node)."""
    d = {}
    for ln in lines:
        d.setdefault(_nk(ln.x1, ln.y1), []).append((ln, 1))
        d.setdefault(_nk(ln.x2, ln.y2), []).append((ln, 2))
    return d


def line_chain(seeds, nodes):
    """The seed lines plus every line joined to them end to end, stopping at junctions
    (a point where three or more lines meet)."""
    seen = {id(l): l for l in seeds}
    stack = list(seeds)
    while stack:
        ln = stack.pop()
        for k in (_nk(ln.x1, ln.y1), _nk(ln.x2, ln.y2)):
            at = nodes.get(k, [])
            if len(at) == 2:
                for other, _ in at:
                    if id(other) not in seen:
                        seen[id(other)] = other
                        stack.append(other)
    return list(seen.values())


def line_grips(ln, nodes):
    """[(kind, key, (x, y))]: a mid grip, plus an end grip on each OPEN end."""
    if abs(ln.x1 - ln.x2) < 1e-9 and abs(ln.y1 - ln.y2) < 1e-9:
        return []
    out = [("mid", 0, ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2))]
    if len(nodes.get(_nk(ln.x1, ln.y1), [])) == 1:
        out.append(("end", 1, (ln.x1, ln.y1)))
    if len(nodes.get(_nk(ln.x2, ln.y2), [])) == 1:
        out.append(("end", 2, (ln.x2, ln.y2)))
    return out


def circle_grip(c):
    return ("radius", 0, (c.cx, c.cy - c.r))


def segment_state(ln, nodes):
    """Everything a mid-grip drag changes: the line and every line joined at its ends,
    with their starting coordinates and the line's unit normal."""
    dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
    n = math.hypot(dx, dy)
    nx, ny = -dy / n, dx / n
    ends = {_nk(ln.x1, ln.y1), _nk(ln.x2, ln.y2)}
    touched = {id(ln): ln}
    for k in ends:
        for other, _ in nodes.get(k, []):
            touched[id(other)] = other
    base = {id(l): (l.x1, l.y1, l.x2, l.y2) for l in touched.values()}
    return {"line": ln, "touched": list(touched.values()), "base": base, "ends": ends, "n": (nx, ny)}


def shift_segment(st, d):
    """Move the segment by d along its normal; joined lines are stretched to follow."""
    nx, ny = st["n"]
    for l in st["touched"]:
        x1, y1, x2, y2 = st["base"][id(l)]
        if _nk(x1, y1) in st["ends"]:
            l.x1, l.y1 = x1 + d * nx, y1 + d * ny
        else:
            l.x1, l.y1 = x1, y1
        if _nk(x2, y2) in st["ends"]:
            l.x2, l.y2 = x2 + d * nx, y2 + d * ny
        else:
            l.x2, l.y2 = x2, y2
