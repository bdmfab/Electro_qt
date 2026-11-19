"""Panel layout helpers (Qt-free): the geometry of panel objects, rail snapping, smart alignment,
the parts still to place and layout checks. Everything is in inches, y up, like the rest of the model."""
from __future__ import annotations
import math
from . import model as m

RAILS = {"DIN 35 x 7.5": (1.378, 0.295), "DIN 35 x 15": (1.378, 0.591), "DIN 15 x 5.5": (0.591, 0.217)}  # width, height
DUCTS = {"1 x 2": (1.0, 2.0), "1.5 x 3": (1.5, 3.0), "2 x 3": (2.0, 3.0), "2 x 4": (2.0, 4.0),
         "3 x 3": (3.0, 3.0), "3 x 4": (3.0, 4.0), "4 x 4": (4.0, 4.0)}                                # width, depth
KIND_NAMES = {"plate": "Back plate", "rail": "DIN rail", "duct": "Wire duct", "part": "Part", "terminals": "Terminal blocks"}
MOUNTED = ("part", "terminals")          # kinds that stand on the plate / a rail and have a mounting line
MM = 25.4


def _quarter(o):
    return int(round(o.rot / 90.0)) % 4


def size(o):
    """(width, height) of the object on the sheet."""
    return (o.w, o.h) if _quarter(o) % 2 == 0 else (o.h, o.w)


def box(o):
    w, h = size(o)
    return o.cx - w / 2, o.cy - h / 2, o.cx + w / 2, o.cy + h / 2


def axis(o):
    """'x' when the object's length runs left-right on the sheet, else 'y'."""
    return "x" if _quarter(o) % 2 == 0 else "y"


def rot_vec(v, deg):
    a = math.radians(deg)
    return v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)


def centerline_offset(o):
    """World offset from the object's centre to its DIN rail centre line (parts)."""
    ox, oy = rot_vec((0.0, o.cl), o.rot)
    return round(ox, 9), round(oy, 9)


def centerline(o):
    """(axis, coordinate across): a rail's centre line, or a rail-mounted part's mounting line."""
    ox, oy = centerline_offset(o) if o.kind in MOUNTED else (0.0, 0.0)
    return ("x", o.cy + oy) if axis(o) == "x" else ("y", o.cx + ox)


def end_points(o):
    """The two ends of a rail / duct's centre line."""
    w, h = size(o)
    return ((o.cx - w / 2, o.cy), (o.cx + w / 2, o.cy)) if axis(o) == "x" else ((o.cx, o.cy - h / 2), (o.cx, o.cy + h / 2))


def set_end(o, which, pt):
    """Move end 0 / 1 of a rail / duct to pt, along its axis; the other end stays put."""
    p0, p1 = end_points(o)
    fixed = p1 if which == 0 else p0
    i = 0 if axis(o) == "x" else 1
    lo, hi = sorted((pt[i], fixed[i]))
    if hi - lo < 0.05:
        return
    if i == 0:
        o.cx = (lo + hi) / 2
    else:
        o.cy = (lo + hi) / 2
    o.w = hi - lo


def rotate(o, pivot, deg):
    o.cx, o.cy = (pivot[0] + rot_vec((o.cx - pivot[0], o.cy - pivot[1]), deg)[0],
                  pivot[1] + rot_vec((o.cx - pivot[0], o.cy - pivot[1]), deg)[1])
    o.rot = (o.rot + deg) % 360


# ------------------------------------------------------------------ placing
def panel_objects(entities):
    return [e for e in entities if isinstance(e, m.PanelObj)]


def snap_box(objs, cx, cy, w, h, tol, gap=0.0, exclude=()):
    """Smart alignment of a box (centre cx, cy; size w x h) to the other objects: its left / centre / right
    (and top / middle / bottom) line up with theirs, or sit `gap` away from a side. Returns (cx, cy, guides);
    guides = [("v", x) | ("h", y)] to draw."""
    xs, ys = [], []
    for o in objs:
        if o in exclude or o.id in {getattr(e, "id", None) for e in exclude}:
            continue
        x0, y0, x1, y1 = box(o)
        xs += [(x0, 0), (x1, 0), ((x0 + x1) / 2, 0), (x1 + gap, 1), (x0 - gap, 2)]   # kinds: align / ghost-left to / ghost-right to
        ys += [(y0, 0), (y1, 0), ((y0 + y1) / 2, 0), (y1 + gap, 1), (y0 - gap, 2)]

    def best(c, half, cands):
        pick, bd = None, tol
        for v, kind in cands:
            for off, want in ((-half, 0), (0.0, 0), (half, 0)):
                if kind == 1 and off != -half:         # ghost's low edge sits above / right of the target
                    continue
                if kind == 2 and off != half:          # ghost's high edge sits below / left of the target
                    continue
                d = abs(c + off - v)
                if d <= bd:
                    pick, bd = (v - off, v), d
        return pick
    gx, gy = best(cx, w / 2, xs), best(cy, h / 2, ys)
    guides = []
    if gx:
        cx = gx[0]; guides.append(("v", gx[1]))
    if gy:
        cy = gy[0]; guides.append(("h", gy[1]))
    return cx, cy, guides


def snap_line(objs, i, v, tol, gap=0.0, exclude=()):
    """Snap one coordinate (i = 0 for x, 1 for y) to the edges / centres of the other objects, or `gap` away
    from their sides. Returns (value, guide coordinate or None)."""
    ids = {getattr(e, "id", None) for e in exclude}
    best, bd = None, tol
    for o in objs:
        if o.id in ids:
            continue
        lo, hi = box(o)[i], box(o)[i + 2]
        for c in (lo, hi, (lo + hi) / 2, hi + gap, lo - gap):
            if abs(c - v) <= bd:
                best, bd = c, abs(c - v)
    return (best, best) if best is not None else (v, None)


def rail_snap(objs, part, cx, cy, tol=0.75):
    """A rail-mounted part near a DIN rail lines its centre line up with the rail's and turns to follow it.
    Returns (cx, cy, rot, rail) or None."""
    best, bd = None, None
    for r in objs:
        if r.kind != "rail":
            continue
        x0, y0, x1, y1 = box(r)
        w, h = size(part)
        reach = max(w, h) / 2 + tol
        if not (x0 - reach <= cx <= x1 + reach and y0 - reach <= cy <= y1 + reach):
            continue
        d = abs(cy - r.cy) if axis(r) == "x" else abs(cx - r.cx)
        if d <= max(w, h) / 2 + tol and (bd is None or d < bd):
            best, bd = r, d
    if best is None:
        return None
    r = best
    want = (0.0, 180.0) if axis(r) == "x" else (90.0, 270.0)
    rot = part.rot if part.rot in want else want[0]
    probe = m.PanelObj("part", 0, 0, part.w, part.h, rot, cl=part.cl)
    ox, oy = centerline_offset(probe)
    if axis(r) == "x":
        x0, _, x1, _ = box(r)
        return min(max(cx, x0), x1), r.cy - oy, rot, r
    _, y0, _, y1 = box(r)
    return r.cx - ox, min(max(cy, y0), y1), rot, r


# ------------------------------------------------------------------ parts from the schematic
def footprint_terminals(blk, qty, cx=0.0, cy=0.0, rot=0.0):
    """A stack of `qty` terminal blocks side by side along the rail (None if the block has no footprint)."""
    one = footprint_part(blk, "", cx, cy, rot)
    if one is None:
        return None
    one.kind, one.qty, one.w = "terminals", max(1, int(qty)), one.w * max(1, int(qty))
    return one


def pinned(e):
    """A locked layout object: it cannot be moved, turned or resized."""
    return isinstance(e, m.PanelObj) and e.locked


def terminal_labels(o):
    """The label of each terminal of a stack (or of one block): the custom name if there is one, else
    ident.number (TB1.1, TB1.2 ...), or just the number when there is no identifier."""
    n = max(1, int(o.qty)) if o.kind == "terminals" else 1
    custom = o.names.split("|") if o.names else []
    out = []
    for i in range(n):
        c = custom[i].strip() if i < len(custom) else ""
        out.append(c or (f"{o.ident}.{o.first + i}" if o.ident else str(o.first + i)))
    return out


def set_terminal_labels(o, ident, first, labels):
    """Store identifier, first number and the edited labels (only those that differ from automatic)."""
    o.ident, o.first = ident.strip(), int(first)
    auto = terminal_labels(m.PanelObj(o.kind, 0, 0, 1, 1, qty=o.qty, ident=o.ident, first=o.first))
    custom = [l.strip() if l.strip() != a else "" for l, a in zip(labels, auto)]
    o.names = "|".join(custom) if any(custom) else ""


def next_ident(project, prefix="TB"):
    """The first unused identifier PREFIX1, PREFIX2 ... over all panel layouts."""
    used = set()
    for sh in project.sheets.values():
        for o in panel_objects(sh.entities):
            if o.ident:
                used.add(o.ident)
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def ungroup(o):
    """The separate blocks of a terminal stack (a list of 'part' objects, no tag), side by side where the
    stack was. The stack's rotation is kept."""
    import copy
    n = max(1, int(o.qty))
    unit = o.w / n
    out = []
    for i in range(n):
        p = copy.deepcopy(o)
        p.id = m.new_id()
        p.kind, p.qty, p.w = "part", 1, unit
        labels = terminal_labels(o)
        p.first = o.first + i
        p.names = labels[i] if (o.names.split("|") + [""] * n)[i].strip() else ""
        dx, dy = rot_vec(((i - (n - 1) / 2.0) * unit, 0.0), o.rot)
        p.cx, p.cy = o.cx + dx, o.cy + dy
        out.append(p)
    return out


def layout_parts(project):
    """{block name: quantity} of the parts that exist only on the panel layouts (terminal stacks and
    untagged parts), without those left out of the BOM."""
    out = {}
    for sh in project.sheets.values():
        if not sh.panel:
            continue
        for o in panel_objects(sh.entities):
            if o.kind not in MOUNTED or o.tag or o.xbom or not o.block:
                continue
            blk = project.blocks.get(o.block)
            if blk is None or blk.exclude_bom:
                continue
            out[o.block] = out.get(o.block, 0) + (o.qty if o.kind == "terminals" else 1)
    return out


def footprint_part(blk, tag, cx=0.0, cy=0.0, rot=0.0):
    """A part object for a block that has a footprint (None if it has none)."""
    if blk is None or blk.fp_w <= 0 or blk.fp_h <= 0 or not blk.mount:
        return None
    return m.PanelObj("part", cx, cy, blk.fp_w, blk.fp_h, rot, depth=blk.fp_d, block=blk.name, tag=tag,
                      mount=blk.mount, cl=blk.rail_cl)


def effective_block(project, blk, tag, profs=None, ref=None):
    """The block as the layout sees it for the part tagged `tag`: its own footprint, replaced by the
    footprint saved on the placed part (props fp_*) or by the profile for its manufacturer + part number."""
    import copy
    from . import profiles as pf
    if blk is None:
        return None
    from .geometry import leaves
    for sh in ([] if ref is not None else project.sheets.values()):
        if sh.panel:
            continue
        for r in leaves(sh.entities):
            if isinstance(r, m.BlockRef) and r.block == blk.name and r.tag == tag:
                ref = r; break
        if ref:
            break
    props = ref.props if ref else {}
    mf = props.get("manufacturer", blk.manufacturer)
    pnum = props.get("part_number", blk.part_number)
    link = props.get("hyperlink", blk.hyperlink)
    out = copy.copy(blk)
    if not blk.mount:                                        # type "Not on back plate": no footprint at all
        return out
    profs = profs if profs is not None else pf.load()
    prof = profs.get(props.get("profile", "")) or pf.find(profs, mf, pnum, link, block=blk.name)[1]
    if prof and prof["width"] > 0 and prof["height"] > 0:
        out.fp_w, out.fp_h, out.fp_d = prof["width"], prof["height"], prof["depth"]
        out.mount, out.rail_cl = prof["mounting"] if prof["mounting"] in ("rail", "plate") else "rail", prof["rail_cl"]
    if "fp_w" in props:                                      # saved on the part itself (no profile key)
        try:
            out.fp_w, out.fp_h, out.fp_d = float(props["fp_w"]), float(props.get("fp_h", 0)), float(props.get("fp_d", 0))
            out.mount, out.rail_cl = props.get("fp_mount", "rail"), float(props.get("fp_cl", 0))
        except ValueError:
            pass
    return out


def needed_parts(project):
    """[(tag, block name)] of every part drawn on the schematic sheets that belongs in the panel
    (not off-page connectors, nothing excluded from the BOM) and has a tag."""
    from .geometry import leaves
    out, seen = [], set()
    for pg, sh in sorted(project.sheets.items()):
        if sh.panel:
            continue
        for r in leaves(sh.entities):
            if not isinstance(r, m.BlockRef) or not r.tag:
                continue
            blk = project.blocks.get(r.block)
            if blk is None or blk.connector or blk.exclude_bom or r.props.get("exclude_bom") == "1":
                continue
            if not blk.mount:                                # "Not on back plate" (field devices ...)
                continue
            if r.tag not in seen:
                seen.add(r.tag); out.append((r.tag, r.block))
    return out


def placed_tags(project):
    return {o.tag for sh in project.sheets.values() if sh.panel for o in panel_objects(sh.entities)
            if o.kind == "part" and o.tag}


def unplaced_parts(project):
    done = placed_tags(project)
    return [(t, b) for t, b in needed_parts(project) if t not in done]


# ------------------------------------------------------------------ checks
def problems(sheet):
    """Plain-language problems of a panel layout: parts overlapping, off the plate, rail parts off a rail."""
    objs = panel_objects(sheet.entities)
    plates = [o for o in objs if o.kind == "plate"]
    parts = [o for o in objs if o.kind in ("part", "duct", "terminals")]
    out = []

    def name(o):
        return o.tag or (f"{o.block} x{o.qty}" if o.kind == "terminals" else o.block) or KIND_NAMES[o.kind]

    def hit(a, b):
        ax0, ay0, ax1, ay1 = box(a); bx0, by0, bx1, by1 = box(b)
        return ax0 < bx1 - 1e-6 and bx0 < ax1 - 1e-6 and ay0 < by1 - 1e-6 and by0 < ay1 - 1e-6

    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            if hit(a, b):
                out.append(f"{name(a)} overlaps {name(b)}")
        if plates:
            px0, py0, px1, py1 = box(plates[0]); x0, y0, x1, y1 = box(a)
            if x0 < px0 - 1e-6 or y0 < py0 - 1e-6 or x1 > px1 + 1e-6 or y1 > py1 + 1e-6:
                out.append(f"{name(a)} is off the back plate")
        if a.kind in MOUNTED and a.mount == "rail":
            ax, c = centerline(a)
            i = 0 if ax == "x" else 1
            lo, hi = box(a)[i], box(a)[i + 2]
            on = [r for r in objs if r.kind == "rail" and axis(r) == ax and abs(centerline(r)[1] - c) < 0.02
                  and box(r)[i] - 1e-6 <= lo and hi <= box(r)[i + 2] + 1e-6]
            if not on:
                out.append(f"{name(a)} is not on a DIN rail")
    return out


# ------------------------------------------------------------------ dimensions
def dim_value(d):
    return abs(d.x2 - d.x1) if d.orient == "h" else abs(d.y2 - d.y1)


def dim_line(d):
    """The two ends of the dimension line."""
    if d.orient == "h":
        return (d.x1, d.pos), (d.x2, d.pos)
    return (d.pos, d.y1), (d.pos, d.y2)


def dim_text(value, units="in"):
    """Dimension text: inches to one decimal (12.5") or whole millimetres (318)."""
    if units == "mm":
        return f"{value * MM:.0f}"
    return f"{value:.1f}\""


def dim_auto_orient(p1, p2):
    return "h" if abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1]) else "v"


def rename_tags(project, renames):
    """Panel parts follow their schematic part when its tag changes. renames: {(block, old tag): new tag},
    applied all at once (so two tags that swap places work). -> number of panel parts renamed."""
    n = 0
    for sh in project.sheets.values():
        if not sh.panel:
            continue
        for o in panel_objects(sh.entities):
            new = renames.get((o.block, o.tag)) if o.kind == "part" and o.tag else None
            if new is not None and new != o.tag:
                o.tag = new
                n += 1
    return n


# ------------------------------------------------------------------ parametric dimensions
_EPS = 1e-9


def anchor_value(o, key):
    x0, y0, x1, y1 = box(o)
    return {"x0": x0, "xc": (x0 + x1) / 2, "x1": x1, "y0": y0, "yc": (y0 + y1) / 2, "y1": y1}[key]


def _parse(a):
    if not a or ":" not in a:
        return None
    i, k = a.rsplit(":", 1)
    return (i, k) if k in ("x0", "xc", "x1", "y0", "yc", "y1") else None


def _ends(byid, d):
    """[(object or None, key or None)] for the two ends of a dimension."""
    out = []
    for a in (d.a1, d.a2):
        p = _parse(a)
        o = byid.get(p[0]) if p else None
        out.append((o, p[1]) if o is not None else (None, None))
    return out


def find_anchor(objs, pt, orient, tol=0.02):
    """The (object, key) whose edge / centre the point sits on (x edges for a horizontal dimension, y for a
    vertical one); the smallest object wins, so a part beats the back plate it stands on."""
    ks = ("x0", "xc", "x1") if orient == "h" else ("y0", "yc", "y1")
    best = None
    for o in objs:
        x0, y0, x1, y1 = box(o)
        if not (x0 - tol <= pt[0] <= x1 + tol and y0 - tol <= pt[1] <= y1 + tol):
            continue
        for k in ks:
            if abs(anchor_value(o, k) - pt[0 if orient == "h" else 1]) <= tol:
                area = (x1 - x0) * (y1 - y0)
                if best is None or area < best[0]:
                    best = (area, o, k)
    return (best[1], best[2]) if best else None


def attach_dim(entities, d):
    """Tie the ends of a dimension to the object edges they sit on (an end on no edge stays free; both ends on
    the same object stay free too - that is the object's own size)."""
    objs = panel_objects(entities)
    hit = [find_anchor(objs, (d.x1, d.y1), d.orient), find_anchor(objs, (d.x2, d.y2), d.orient)]
    if hit[0] and hit[1] and hit[0][0] is hit[1][0]:
        hit = [None, None]
    d.a1 = f"{hit[0][0].id}:{hit[0][1]}" if hit[0] else ""
    d.a2 = f"{hit[1][0].id}:{hit[1][1]}" if hit[1] else ""
    return bool(d.a1 or d.a2)


def attach_all(entities):
    """Dimensions drawn before they could be attached: attach those whose ends sit on object edges."""
    n = 0
    for d in entities:
        if isinstance(d, m.Dim) and not d.a1 and not d.a2 and attach_dim(entities, d):
            n += 1
    return n


def sync_dims(entities):
    """Attached dimension ends follow their objects (derived data: always recomputed from the objects)."""
    byid = {o.id: o for o in panel_objects(entities)}
    changed = False
    for d in entities:
        if not isinstance(d, m.Dim):
            continue
        for i, (o, k) in enumerate(_ends(byid, d)):
            if o is None:
                continue
            v = anchor_value(o, k)
            x0, y0, x1, y1 = box(o)
            if d.orient == "h":
                x, y = (d.x1, d.y1) if i == 0 else (d.x2, d.y2)
                nx, ny = v, min(max(y, y0), y1)
            else:
                x, y = (d.x1, d.y1) if i == 0 else (d.x2, d.y2)
                nx, ny = min(max(x, x0), x1), v
            if abs(nx - x) > _EPS or abs(ny - y) > _EPS:
                if i == 0:
                    d.x1, d.y1 = nx, ny
                else:
                    d.x2, d.y2 = nx, ny
                changed = True
    return changed


def propagate(entities, shifts):
    """shifts {object id: [dx, dy]}: objects that are moving. Every unlocked object dimensioned to a moving one
    follows it along the dimension's direction so the dimension keeps its value; the chain goes on through
    further dimensions and stops at locked objects (their dimension just changes). Adds to `shifts`."""
    byid = {o.id: o for o in panel_objects(entities)}
    dims = [d for d in entities if isinstance(d, m.Dim)]
    queue = list(shifts)
    guard = 0
    while queue and guard < 10000:
        guard += 1
        oid = queue.pop()
        for d in dims:
            (o1, _), (o2, _) = _ends(byid, d)
            if o1 is None or o2 is None or o1 is o2:
                continue
            if oid == o1.id:
                other = o2
            elif oid == o2.id:
                other = o1
            else:
                continue
            ax = 0 if d.orient == "h" else 1
            c = shifts[oid][ax]
            if abs(c) < _EPS or other.locked:
                continue
            cur = shifts.setdefault(other.id, [0.0, 0.0])
            if abs(cur[ax]) > _EPS:
                continue                          # already moving along that direction
            cur[ax] = c
            queue.append(other.id)
    return shifts


def dim_signed(d):
    return (d.x2 - d.x1) if d.orient == "h" else (d.y2 - d.y1)


def plan_dim_value(entities, d, new):
    """Change a dimension to `new`: both ends unlocked -> both objects move, half each; one locked -> the other
    moves the whole way; both locked -> refused. -> (shifts {id: [dx, dy]}, message); shifts is None when
    refused, {} when neither end is attached to an object (the caller moves the free point)."""
    byid = {o.id: o for o in panel_objects(entities)}
    (o1, _), (o2, _) = _ends(byid, d)
    cur = dim_signed(d)
    sign = -1.0 if cur < 0 else 1.0
    diff = sign * new - cur
    if abs(diff) < _EPS:
        return {}, ""
    if o1 is None and o2 is None:
        return {}, ""
    ax = 0 if d.orient == "h" else 1
    free1 = o1 is not None and not o1.locked
    free2 = o2 is not None and not o2.locked
    shifts = {}
    if free1 and free2:
        shifts[o1.id] = [0.0, 0.0]; shifts[o2.id] = [0.0, 0.0]
        shifts[o1.id][ax] = -diff / 2
        shifts[o2.id][ax] = diff / 2
    elif free2:
        shifts[o2.id] = [0.0, 0.0]; shifts[o2.id][ax] = diff
    elif free1:
        shifts[o1.id] = [0.0, 0.0]; shifts[o1.id][ax] = -diff
    else:
        return None, "Both ends of this dimension are locked - unlock one to change it."
    propagate(entities, shifts)
    return shifts, ""


def shift_mods(entities, shifts, skip=()):
    """[(object, {cx, cy})] that apply the shifts (objects in `skip` are left to the caller)."""
    byid = {o.id: o for o in panel_objects(entities)}
    return [(byid[i], {"cx": byid[i].cx + dx, "cy": byid[i].cy + dy}) for i, (dx, dy) in shifts.items()
            if i in byid and i not in skip and (abs(dx) > _EPS or abs(dy) > _EPS)]
