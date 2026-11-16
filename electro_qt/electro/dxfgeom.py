"""Open a DXF as geometry (Qt-free): lines, arcs, circles, polylines (with arc segments), ellipses
(approximated), text, and the drawing's own blocks. Coordinates are scaled to inches.

Not brought across: splines, hatches, solids, dimensions, images and 3D objects (they are counted
and reported); MTEXT formatting becomes plain text."""
from __future__ import annotations
import copy
import math
import re
from dataclasses import dataclass, field
from . import model as m
from .dxfread import read_dxf, RawEntity
from .dxfimport import clean_mtext
from .geometry import bounds, translate

UNITS = {"Inches": 1.0, "Feet": 12.0, "Millimeters": 1 / 25.4, "Centimeters": 1 / 2.54, "Meters": 1000 / 25.4}
INSUNITS = {1: "Inches", 2: "Feet", 4: "Millimeters", 5: "Centimeters", 6: "Meters"}
SKIPPED = ("SPLINE", "HATCH", "SOLID", "TRACE", "3DFACE", "DIMENSION", "LEADER", "IMAGE", "POINT", "VIEWPORT",
           "RAY", "XLINE", "MLINE", "WIPEOUT", "REGION", "BODY", "3DSOLID", "TOLERANCE", "MLEADER")
_SYSTEM_BLOCKS = re.compile(r"^(\*|A\$C)", re.I)


@dataclass
class GeomResult:
    entities: list = field(default_factory=list)
    blocks: dict = field(default_factory=dict)       # name -> BlockDef (new names)
    layers: dict = field(default_factory=dict)       # name -> Layer
    stats: dict = field(default_factory=dict)        # what came in / what was skipped
    renamed: dict = field(default_factory=dict)      # DXF block name -> name used here


def check_ascii(path) -> None:
    with open(path, "rb") as f:
        head = f.read(22)
    if head.startswith(b"AutoCAD Binary DXF"):
        raise ValueError("This is a binary DXF. Save it as an ASCII DXF and open it again.")


def file_units(path):
    """Unit name from the file's $INSUNITS ('Millimeters' ...) or None when it has none."""
    check_ascii(path)
    raw = read_dxf(path)
    try:
        return INSUNITS.get(int(raw.header.get("$INSUNITS", "0")))
    except ValueError:
        return None


# ------------------------------------------------------------------ small helpers
def _style(e: RawEntity, raw) -> m.Style:
    col = None
    try:
        c = int(e.get(62, "256"))
        if 1 <= c <= 255:
            col = c
    except ValueError:
        pass
    lt = (e.get(6, "") or "").upper()
    if not lt or lt in ("BYLAYER", "BYBLOCK"):
        lt = raw.layer_lt.get(e.get(8, "0"), "CONTINUOUS").upper()
    return m.Style(layer=e.get(8, "0"), color=col, linetype=_linetype(lt))


def _linetype(name: str) -> str:
    n = name.upper()
    if "DOT" in n:
        return "dotted"
    if any(k in n for k in ("DASH", "HIDDEN", "CENTER", "PHANTOM", "DIVIDE", "BORDER")):
        return "dashed"
    return "continuous"


def _extrusion_flip(e: RawEntity) -> bool:
    try:
        return float(e.get(230, "1")) < 0
    except ValueError:
        return False


def bulge_arc(p1, p2, b, st):
    """Arc for a polyline segment with bulge b (CCW from p1 to p2 when b > 0), or None for a straight one."""
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if abs(b) < 1e-9 or d < 1e-12:
        return None
    theta = 4 * math.atan(b)                           # included angle, signed
    r = d / (2 * math.sin(abs(theta) / 2))
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    h = r * math.cos(abs(theta) / 2)                   # centre distance from the chord
    nx, ny = -(p2[1] - p1[1]) / d, (p2[0] - p1[0]) / d     # left normal of p1 -> p2
    sgn = 1 if b > 0 else -1
    if abs(theta) > math.pi:
        sgn = -sgn
    cx, cy = mx + nx * h * sgn, my + ny * h * sgn
    a1 = math.degrees(math.atan2(p1[1] - cy, p1[0] - cx)) % 360
    a2 = math.degrees(math.atan2(p2[1] - cy, p2[0] - cx)) % 360
    s, e = (a1, a2) if b > 0 else (a2, a1)
    return m.Arc(cx, cy, r, s, e, st)


def _vertices(e: RawEntity):
    """[(x, y, bulge)] of a LWPOLYLINE."""
    out = []
    for c, v in e.codes:
        try:
            if c == 10:
                out.append([float(v), 0.0, 0.0])
            elif c == 20 and out:
                out[-1][1] = float(v)
            elif c == 42 and out:
                out[-1][2] = float(v)
        except ValueError:
            pass
    return [tuple(v) for v in out]


def _poly_entities(verts, closed, st, stats):
    out = []
    n = len(verts)
    segs = n if closed else n - 1
    for i in range(max(0, segs)):
        a, b = verts[i], verts[(i + 1) % n]
        arc = bulge_arc(a[:2], b[:2], a[2], st)
        if arc is not None:
            out.append(arc)
        elif math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-12:
            out.append(m.Line(a[0], a[1], b[0], b[1], st))
    stats["polylines"] = stats.get("polylines", 0) + 1
    return out


def merge_polylines(raws):
    """Old style POLYLINE + VERTEX ... SEQEND become one entity with the vertices' codes (10 / 20 / 42 repeated)."""
    out, i = [], 0
    while i < len(raws):
        e = raws[i]
        if e.type == "POLYLINE":
            poly = RawEntity("POLYLINE", [c for c in e.codes if c[0] in (8, 62, 6, 70)])
            i += 1
            while i < len(raws) and raws[i].type != "SEQEND":
                if raws[i].type == "VERTEX":
                    poly.codes += [c for c in raws[i].codes if c[0] in (10, 20, 42)]
                i += 1
            i += 1                                       # SEQEND
            out.append(poly)
        elif e.type in ("VERTEX", "SEQEND"):
            i += 1
        else:
            out.append(e)
            i += 1
    return out


def _ellipse(e: RawEntity, st, k):
    cx, cy = e.getf(10), e.getf(20)
    mx, my = e.getf(11), e.getf(21)
    ratio = e.getf(40, 1.0)
    t0, t1 = e.getf(41, 0.0), e.getf(42, 2 * math.pi)
    if t1 <= t0:
        t1 += 2 * math.pi
    nx, ny = -my * ratio, mx * ratio                     # minor axis vector
    n = max(12, int(48 * (t1 - t0) / (2 * math.pi)))
    pts = [(cx + mx * math.cos(t) + nx * math.sin(t), cy + my * math.cos(t) + ny * math.sin(t))
           for t in (t0 + (t1 - t0) * i / n for i in range(n + 1))]
    return [m.Line(a[0] * k, a[1] * k, b[0] * k, b[1] * k, st) for a, b in zip(pts, pts[1:])]


_ATTACH_COL = {0: "left", 1: "center", 2: "right"}


def _text(e: RawEntity, st, k):
    h = e.getf(40, 0.1) * k
    rot = e.getf(50)
    if e.type == "MTEXT":
        raw_ = "".join(e.all(3)) + e.get(1, "")
        txt = clean_mtext(raw_)
        ap = int(e.get(71, "1") or 1)
        align = _ATTACH_COL[(ap - 1) % 3]
        row = (ap - 1) // 3
        n = txt.count("\n") + 1
        x, y = e.getf(10) * k, e.getf(20) * k
        if e.get(11) is not None:
            rot = math.degrees(math.atan2(e.getf(21), e.getf(11)))
        first = {0: y - h, 1: y + n * h * 1.667 / 2 - h, 2: y + (n - 1) * h * 1.667}[row]
        return m.Text(x, first, txt, txt, h, rot, st, align=align)
    txt = e.get(1, "")
    if e.type == "ATTDEF" and not txt.strip():
        return None
    ha, va = int(e.get(72, "0") or 0), int(e.get(73, "0") or 0)
    x, y = e.getf(10) * k, e.getf(20) * k
    align = "left"
    if ha in (1, 2, 4) or va:
        x, y = e.getf(11) * k, e.getf(21) * k
        align = {1: "center", 2: "right", 4: "center"}.get(ha, "left")
        y -= {3: h, 2: h / 2, 1: -0.2 * h}.get(va, 0.0)
    return m.Text(x, y, txt, txt, h, rot, st, align=align)


# ------------------------------------------------------------------ conversion
class _Importer:
    def __init__(self, raw, k, taken_blocks):
        self.raw, self.k = raw, k
        self.taken = set(taken_blocks)
        self.stats = {}
        self.renamed = {}
        self.blocks = {}
        self.used_layers = set()

    def count(self, key, n=1):
        self.stats[key] = self.stats.get(key, 0) + n

    def block_name(self, name):
        if name not in self.renamed:
            new, i = name, 1
            while new in self.taken or new in self.blocks.values():
                i += 1
                new = f"{name}_dxf" if i == 2 else f"{name}_dxf{i}"
            self.renamed[name] = new
        return self.renamed[name]

    def convert(self, e: RawEntity, k=None):
        k = self.k if k is None else k
        t = e.type
        st = _style(e, self.raw)
        self.used_layers.add(st.layer)
        f = e.getf
        flip = _extrusion_flip(e)
        if t == "LINE":
            return [m.Line(f(10) * k, f(20) * k, f(11) * k, f(21) * k, st)]
        if t == "CIRCLE":
            return [m.Circle((-f(10) if flip else f(10)) * k, f(20) * k, f(40) * k, st)]
        if t == "ARC":
            cx, a0, a1 = f(10), f(50), f(51)
            if flip:
                cx, a0, a1 = -cx, 180 - a1, 180 - a0
            return [m.Arc(cx * k, f(20) * k, f(40) * k, a0 % 360, a1 % 360, st)]
        if t == "LWPOLYLINE":
            v = [(x * k, y * k, b) for x, y, b in _vertices(e)]
            return _poly_entities(v, int(e.get(70, "0") or 0) & 1, st, self.stats)
        if t == "POLYLINE":
            v = [(x * k, y * k, b) for x, y, b in _vertices(e)]
            return _poly_entities(v, int(e.get(70, "0") or 0) & 1, st, self.stats)
        if t == "ELLIPSE":
            self.count("ellipses (approximated by lines)")
            return _ellipse(e, st, k)
        if t in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
            if t in ("ATTRIB", "ATTDEF") and int(e.get(70, "0") or 0) & 1:
                return []                                   # invisible attribute
            tx = _text(e, st, k)
            return [tx] if tx is not None and tx.source.strip() else []
        if t == "INSERT":
            return self.insert(e, st)
        self.count("skipped " + t)
        return []

    def insert(self, e, st):
        name = e.get(2, "")
        if name not in self.raw.blocks or _SYSTEM_BLOCKS.match(name):
            self.count("skipped INSERT of " + name) if name else None
            return []
        self.ensure_block(name)
        sx, sy = e.getf(41, 1.0), e.getf(42, 1.0)
        rot = e.getf(50)
        x, y = e.getf(10) * self.k, e.getf(20) * self.k
        if abs(abs(sx) - abs(sy)) < 1e-9 and abs(abs(sx) - 1.0) < 1e-9:
            mirror = (sx < 0) != (sy < 0)                   # one flipped axis = a mirror; the other flip is a half turn
            if sy < 0:
                rot += 180.0
            ref = m.BlockRef(self.block_name(name), x, y, rot % 360, mirror, style=st)
            return [ref]
        # scaled insert: the block's geometry is placed as plain objects
        self.count(f"inserts of {name} exploded (scaled)")
        ents = []
        for r in merge_polylines(self.raw.blocks[name]):
            if r.type in ("TEXT", "ATTDEF") and r.get(1, "").strip().lower() == "wire#":
                continue                                    # a wire number slot marker, not drawing
            ents += self.convert(r)
        return transform(ents, sx, sy, rot, x, y)

    def ensure_block(self, name):
        new = self.block_name(name)
        if new in self.blocks:
            return
        self.blocks[new] = None                              # guards against recursion
        self.blocks[new] = self.make_block(new, self.raw.blocks[name])

    def make_block(self, name, raws):
        b = m.BlockDef(name)
        for r in merge_polylines(raws):
            if r.type in ("TEXT", "ATTDEF") and r.get(1, "").strip().lower() == "wire#":
                b.slots.append(m.Slot("", r.getf(10) * self.k, r.getf(20) * self.k))
            else:
                b.entities.extend(self.convert(r))
        for i, s in enumerate(b.slots, 1):
            s.terminal = f"T{i}"
        b.poles = max(1, len(b.slots) // 2)
        return b


def transform(ents, sx, sy, rot_deg, dx, dy):
    """Scale (sx, sy), rotate, move: plain objects. Circles keep the mean radius, arcs flip with a mirror."""
    th = math.radians(rot_deg)
    c, s = math.cos(th), math.sin(th)

    def pt(x, y):
        x, y = x * sx, y * sy
        return x * c - y * s + dx, x * s + y * c + dy

    det = sx * sy
    r = (abs(sx) + abs(sy)) / 2
    out = []
    for e in ents:
        if isinstance(e, m.Line):
            e.x1, e.y1 = pt(e.x1, e.y1)
            e.x2, e.y2 = pt(e.x2, e.y2)
        elif isinstance(e, m.Circle):
            e.cx, e.cy = pt(e.cx, e.cy)
            e.r *= r
        elif isinstance(e, m.Arc):
            def ang(a):
                ax, ay = math.cos(math.radians(a)) * sx, math.sin(math.radians(a)) * sy
                return math.degrees(math.atan2(ax * s + ay * c, ax * c - ay * s)) % 360
            a0, a1 = ang(e.start), ang(e.end)
            e.start, e.end = (a1, a0) if det < 0 else (a0, a1)
            e.cx, e.cy = pt(e.cx, e.cy)
            e.r *= r
        elif isinstance(e, m.Text):
            e.x, e.y = pt(e.x, e.y)
            e.rotation = (e.rotation + rot_deg) % 360
            e.height *= r
        elif isinstance(e, m.BlockRef):
            e.x, e.y = pt(e.x, e.y)
            e.rotation = (e.rotation + rot_deg + (180 if sy < 0 else 0)) % 360
            if sx < 0:
                e.mirror = not e.mirror
        out.append(e)
    return out


def import_geometry(path, scale: float, existing_blocks=(), existing_layers=()) -> GeomResult:
    """Everything in the DXF's model space as Electro_qt objects, in inches (`scale` converts the file's units).
    Blocks the drawing places come as BlockDefs (renamed when the name is taken); layers as Layer objects."""
    check_ascii(path)
    raw = read_dxf(path)
    imp = _Importer(raw, scale, existing_blocks)
    res = GeomResult()
    for e in merge_polylines(raw.entities):
        res.entities += imp.convert(e)
    res.blocks = {n: b for n, b in imp.blocks.items() if b is not None}
    for n in sorted(imp.used_layers):
        if n not in existing_layers:
            res.layers[n] = m.Layer(n, abs(raw.layers.get(n, 7)) or 7, "graphics", linetype=_linetype(raw.layer_lt.get(n, "")))
    for b in res.blocks.values():
        for e in b.entities:
            ly = getattr(getattr(e, "style", None), "layer", None)
            if ly and ly not in existing_layers and ly not in res.layers:
                res.layers[ly] = m.Layer(ly, abs(raw.layers.get(ly, 7)) or 7, "graphics", linetype=_linetype(raw.layer_lt.get(ly, "")))
    res.stats = dict(imp.stats)
    res.stats["objects"] = len(res.entities)
    res.stats["blocks"] = len(res.blocks)
    res.renamed = {a: b for a, b in imp.renamed.items() if a != b}
    return res


def scratch_sheet(res: GeomResult, title: str) -> m.Sheet:
    """A sheet (not part of the project) holding the imported geometry, moved so its lower left sits at (1, 1)."""
    box = bounds(res.entities, res.blocks) or (0.0, 0.0, 10.0, 8.0)
    dx, dy = 1.0 - box[0], 1.0 - box[1]
    for e in res.entities:
        translate(e, dx, dy)
    sh = m.Sheet(98, title)
    sh.width = max(12.0, box[2] - box[0] + 2.0)
    sh.height = max(8.0, box[3] - box[1] + 2.0)
    sh.entities = res.entities
    return sh
