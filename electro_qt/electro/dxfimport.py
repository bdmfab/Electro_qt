"""DXF -> Electro_qt Project (single sheet). Uses the stdlib reader."""
from __future__ import annotations
import re
from . import model as m
from .dxfread import read_dxf, RawEntity

WIRE_LAYERS = {"L1": "AC", "L2": "AC", "L3": "AC", "WIRE_DC": "DC"}
SCHEMES = {"AC": "<incident><L|T><phase>", "DC": "<page><zone><incident>"}
_MTEXT_FMT = re.compile(r"\\[A-Za-z][^;\\]*;|[{}]")


def clean_mtext(s: str) -> str:
    s = s.replace("\\P", "\n").replace("\\~", " ")
    return _MTEXT_FMT.sub("", s)


def _style(e: RawEntity, layers) -> m.Style:
    return m.Style(layer=e.get(8, "0"))


def convert(e: RawEntity, layers, stats):
    """Return list of model entities for one raw DXF entity."""
    t = e.type
    st = _style(e, layers)
    f = e.getf
    if t == "LINE":
        ln = m.Line(f(10), f(20), f(11), f(21), st)
        if st.layer in WIRE_LAYERS:
            ln.number = m.WireNumber("auto", "")
        return [ln]
    if t == "CIRCLE":
        return [m.Circle(f(10), f(20), f(40), st)]
    if t == "ARC":
        return [m.Arc(f(10), f(20), f(40), f(50), f(51), st)]
    if t in ("TEXT", "ATTRIB", "ATTDEF"):
        return [m.Text(f(10), f(20), e.get(1, ""), e.get(1, ""), f(40, 0.1), f(50), st)]
    if t == "MTEXT":
        raw = "".join(e.all(3)) + e.get(1, "")
        return [m.Text(f(10), f(20), clean_mtext(raw), clean_mtext(raw), f(40, 0.1), f(50), st)]
    if t == "LWPOLYLINE":
        xs = [float(v) for v in e.all(10)]
        ys = [float(v) for v in e.all(20)]
        pts = list(zip(xs, ys))
        closed = int(e.get(70, "0")) & 1
        if closed and len(pts) > 2:
            pts.append(pts[0])
        stats["polylines_to_lines"] += 1
        return [m.Line(a[0], a[1], b[0], b[1], st) for a, b in zip(pts, pts[1:])]
    if t == "INSERT":
        return [m.BlockRef(e.get(2), f(10), f(20), f(50), style=st)]
    stats["skipped_" + t] = stats.get("skipped_" + t, 0) + 1
    return []


def import_block(name, raws, layers, stats) -> m.BlockDef:
    b = m.BlockDef(name)
    for r in raws:
        if r.type in ("TEXT", "ATTDEF") and (r.get(1, "").strip().lower() == "wire#"):
            b.slots.append(m.Slot("", r.getf(10), r.getf(20)))
        else:
            b.entities.extend(convert(r, layers, stats))
    for i, s in enumerate(b.slots, 1):
        s.terminal = f"T{i}"       # drafter names terminals later
    b.poles = max(1, len(b.slots) // 2)
    return b


def import_dxf(path, name=None, page=1) -> tuple[m.Project, dict]:
    raw = read_dxf(path)
    stats = {"polylines_to_lines": 0}
    p = m.Project(name or "Imported")
    for lname, color in raw.layers.items():
        wire = lname in WIRE_LAYERS
        p.layers[lname] = m.Layer(lname, abs(color), "wire" if wire else "graphics",
                                  numbered=wire, scheme=SCHEMES.get(WIRE_LAYERS.get(lname), ""))
    sheet = p.add_sheet(m.Sheet(page, name or ""))
    used = set()
    for e in raw.entities:
        sheet.entities.extend(convert(e, raw.layers, stats))
        if e.type == "INSERT":
            used.add(e.get(2))
    # pull in used blocks, plus nested ones
    todo = list(used)
    while todo:
        bn = todo.pop()
        if bn in p.blocks or bn not in raw.blocks:
            continue
        p.blocks[bn] = import_block(bn, raw.blocks[bn], raw.layers, stats)
        for r in raw.blocks[bn]:
            if r.type == "INSERT":
                todo.append(r.get(2))
    return p, stats
