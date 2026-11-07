"""Block (library part) logic, Qt-free: placing, tags, slots, trimming wires."""
from __future__ import annotations
import copy
import math
from . import model as m
from . import fields
from .geometry import (clone_entity, leaves, rotate_entity, mirror_entity, translate, bounds)
from .templates import zone_of


# ------------------------------------------------------------ placement geometry
def _to_world(p, ref):
    x, y = p
    if ref.mirror:
        x = -x
    r = math.radians(ref.rotation)
    c, s = math.cos(r), math.sin(r)
    return ref.x + x * c - y * s, ref.y + x * s + y * c


def block_slots(block: m.BlockDef, ref: m.BlockRef):
    """[(Slot, (x, y))] with the instance's rotation / mirror / position applied."""
    return [(s, _to_world((s.x, s.y), ref)) for s in block.slots]


def block_entities(block: m.BlockDef, ref: m.BlockRef):
    """World-space copies of the block's graphics for one instance. Text stays upright."""
    out = []
    for e in block.entities:
        c = clone_entity(e)
        upright = {id(t): t.rotation for t in leaves([c]) if isinstance(t, m.Text)}
        try:
            if ref.mirror:
                mirror_entity(c, "v", 0.0)
            if ref.rotation % 360:
                rotate_entity(c, (0.0, 0.0), ref.rotation)
        except ValueError:                      # a rectangle at an odd angle: keep it unrotated
            c = clone_entity(e)
        for t in leaves([c]):
            if isinstance(t, m.Text) and id(t) in upright:
                t.rotation = upright[id(t)]
        translate(c, ref.x, ref.y)
        out.append(c)
    return out


def xref_index(project):
    """Where everything is, for cross-references: {"loc": {ref.id: "pp/zz"}, "linked": {coil id:
    [contact ids]}, "conn": {connector name: [ref ids]}}."""
    loc, linked, conn = {}, {}, {}
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        for r in leaves(sh.entities):
            if not isinstance(r, m.BlockRef):
                continue
            loc[r.id] = f"{pg:02d}/{zone_text(sh, r.x, r.y)}"
            if r.props.get("tag_mode") == "linked" and r.props.get("tag_link"):
                linked.setdefault(r.props["tag_link"], []).append(r.id)
            blk = project.blocks.get(r.block)
            if blk is not None and blk.connector and r.tag:
                conn.setdefault(r.tag, []).append(r.id)
    return {"loc": loc, "linked": linked, "conn": conn}


def xref_text(project, ref, index=None):
    """Cross-reference of one placed part: a coil lists where its linked contacts are, a
    contact shows where its coil is, an off-page connector lists the other connectors with the
    same name. Locations are page/zone."""
    ix = index or xref_index(project)
    blk = project.blocks.get(ref.block)
    if blk is not None and blk.connector:
        return ", ".join(sorted(ix["loc"][i] for i in ix["conn"].get(ref.tag, []) if i != ref.id))
    if ref.props.get("tag_mode") == "linked":
        return ix["loc"].get(ref.props.get("tag_link"), "")
    return ", ".join(sorted(ix["loc"][i] for i in ix["linked"].get(ref.id, []) if i in ix["loc"]))


def block_layer_names(blk: m.BlockDef):
    """Layers used by a block's graphics, in first-use order."""
    out = []
    for e in leaves(blk.entities):
        n = e.style.layer
        if n not in out:
            out.append(n)
    return out


def capture_layers(project: m.Project, blk: m.BlockDef) -> None:
    """Remember the definitions (colour, linetype, weight ...) of the layers the block uses,
    so the block brings them along into any project."""
    import copy
    for n in block_layer_names(blk):
        if n in project.layers:
            blk.layers[n] = copy.deepcopy(project.layers[n])


def default_layer(name: str) -> m.Layer:
    """A layer made on the fly for a block that did not bring its own definition: named after what it
    holds (a 'dashed' layer is dashed, a 'gray' layer is gray)."""
    n = name.lower()
    lay = m.Layer(name)
    if "dash" in n:
        lay.linetype = "dashed"
    if "gray" in n or "grey" in n:
        lay.color = 8
    return lay


def ensure_layers(project: m.Project, blk: m.BlockDef) -> list:
    """Add the layers a block's graphics use that this project lacks: the definition stored
    with the block, else a plain default layer. -> names added."""
    import copy
    added = []
    for n in block_layer_names(blk):
        if n not in project.layers:
            project.layers[n] = copy.deepcopy(blk.layers[n]) if n in blk.layers else default_layer(n)
            added.append(n)
    return added


def default_connector_block(kind="from") -> m.BlockDef:
    """Ready-made off-page connectors, one slot each (the wire attaches there). 'GOTO From':
    wire at the flat back of the arrow, shows the cross-reference to its right. 'GOTO To': wire at
    the tip (front), no text (the wire number already says where it goes). Rotate / mirror when
    placing to suit the wire direction."""
    if kind == "from":
        pts = [(0, 0.1), (0.38, 0.1), (0.5, 0), (0.38, -0.1), (0, -0.1)]
        name, lines = "From", ("xref",)
    else:
        pts = [(0, 0), (-0.12, 0.1), (-0.5, 0.1), (-0.5, -0.1), (-0.12, -0.1)]    # turned 180: body on the left
        name, lines = "To", ()
    ents = [m.Line(*pts[i], *pts[(i + 1) % 5], m.Style("0")) for i in range(5)]
    ents.append(m.SlotMark(0, 0, ""))
    blk = make_block(name, ents, (0, 0), lines, "right", description="Off-page connector " + kind,
                     connector=1, poles=1, folder="GOTO")
    for t in blk.entities:                           # the name sits beside the arrow, centred on it
        if isinstance(t, m.Text):
            t.y -= 0.1
    return blk


def block_context(project: m.Project, sheet: m.Sheet, block: m.BlockDef, ref: m.BlockRef) -> dict:
    ctx = fields.context(project, sheet)
    for k, v in block.data.items():
        ctx[k] = str(v)
    desc = ref.props.get("description", block.description)
    part = ref.props.get("part_number", block.part_number)
    ctx.update(xref=xref_text(project, ref), tag=ref.tag, description=desc, desc=desc, part=part,
               part_label=("#" + part) if part else "",
               manufacturer=ref.props.get("manufacturer", block.manufacturer),
               hyperlink=block.hyperlink)
    return ctx


def resolved_entities(project, sheet, block, ref):
    """block_entities with field codes ({tag}, {description}, {part_label}, ...) filled in."""
    ctx = block_context(project, sheet, block, ref)
    ents = block_entities(block, ref)
    hidden = {"{" + k + "}" for k in ref.props.get("hide", "").split(",") if k}
    for t in leaves(ents):
        if isinstance(t, m.Text):
            t.resolved = "" if t.source in hidden else fields.resolve(t.source, ctx)
            t.hidden = t.resolved == "" and t.source != ""       # blank value: draw nothing (not the {code})
    return ents


# ------------------------------------------------------------ tags
def zone_text(sheet, x, y):
    return f"{zone_of(sheet, x, y):02d}"


def assign_tag(project: m.Project, block: m.BlockDef, sheet: m.Sheet, x, y, skip=None, extra_taken=()) -> str:
    """<prefix><page><zone>, plus A, B, ... when another automatic tag already has it
    (same prefix, page and zone). Typed or picked tags never cause a letter."""
    if not block.tag_prefix:
        return ""
    base = f"{block.tag_prefix}{sheet.page:02d}{zone_text(sheet, x, y)}"
    taken = {r.tag for s in project.sheets.values() for r in leaves(s.entities)
             if isinstance(r, m.BlockRef) and r is not skip
             and r.props.get("tag_mode") not in ("manual", "linked")}
    taken |= set(extra_taken)
    if base not in taken:
        return base
    for i in range(26):
        cand = base + chr(ord("A") + i)
        if cand not in taken:
            return cand
    return base + "?"


# ------------------------------------------------------------ making a block
def explode_rect(r: m.Rect):
    pts = [(r.x, r.y), (r.x + r.w, r.y), (r.x + r.w, r.y + r.h), (r.x, r.y + r.h)]
    return [m.Line(*pts[i], *pts[(i + 1) % 4], m.Style(**vars(r.style))) for i in range(4)]


LABEL_CODES = ("{description}", "{part_label}", "{tag}", "{xref}")      # top to bottom


def label_lines_of(block: m.BlockDef):
    """Which stacked-label lines the block currently shows ('description', 'part_label', 'tag')."""
    have = {t.source for t in block.entities if isinstance(t, m.Text)}
    return tuple(c[1:-1] for c in LABEL_CODES if c in have)


def rebuild_label(block: m.BlockDef, lines, pos="above"):
    """Replace the block's stacked label. lines: any of description / part_label / tag.
    'above': centred over the part, description on top, tag next to the part.
    'right': left-aligned beside the part."""
    block.entities[:] = [e for e in block.entities
                         if not (isinstance(e, m.Text) and e.source in LABEL_CODES)]
    block.label_pos = pos
    lines = [k for k in ("description", "part_label", "tag", "xref") if k in lines]
    if not lines:
        return
    bb = bounds(block.entities) or (0.0, 0.0, 0.0, 0.0)
    if pos == "center":                                   # small text inside the part, centred
        cx, cy, n = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2, len(lines)
        for k, key in enumerate(lines):
            block.entities.append(m.Text(cx, cy + (n - 1) * 0.045 - 0.035 - k * 0.09, "{" + key + "}", "", 0.07, 0.0,
                                         m.Style("0"), align="center"))
        return
    xs, ys = [bb[0], bb[2]], [bb[1], bb[3]]
    for s in block.slots:
        xs.append(s.x); ys.append(s.y)
    x0, x1, y1 = min(xs), max(xs), max(ys)
    if pos == "right":
        y = y1 - 0.05
        for key in lines:
            block.entities.append(m.Text(x1 + 0.1, y, "{" + key + "}", "", 0.1, 0.0, m.Style("0"), align="left"))
            y -= 0.16
    else:
        y = y1 + 0.1
        for key in reversed(lines):                       # tag first (nearest the part), then upward
            block.entities.append(m.Text((x0 + x1) / 2, y, "{" + key + "}", "", 0.1, 0.0,
                                         m.Style("0"), align="center"))
            y += 0.16


def make_block(name, entities, base, label_lines=(), label_pos="above", **data) -> m.BlockDef:
    """BlockDef from drawn objects. SlotMarks become slots; rectangles are exploded
    (so the block can rotate); everything is stored relative to `base`."""
    ents, slots = [], []
    for e in entities:
        for leaf in leaves([clone_entity(e)]):
            if isinstance(leaf, m.SlotMark):
                slots.append(m.Slot(leaf.terminal, round(leaf.x - base[0], 9), round(leaf.y - base[1], 9)))
            elif isinstance(leaf, m.Rect):
                ents.extend(explode_rect(leaf))
            else:
                ents.append(leaf)
    for e in ents:
        translate(e, -base[0], -base[1])
        for leaf in leaves([e]):
            if isinstance(leaf, m.Line):
                leaf.x1, leaf.y1, leaf.x2, leaf.y2 = (round(v, 9) for v in (leaf.x1, leaf.y1, leaf.x2, leaf.y2))
    b = m.BlockDef(name, entities=ents, slots=slots, **data)
    b.poles = data.get("poles") or max(1, len(slots) // 2)
    rebuild_label(b, label_lines, label_pos)
    return b


# ------------------------------------------------------------ edit a block's geometry
EDIT_ORIGIN = (6.0, 6.0)          # where the block's origin sits on its editing sheet


def edit_sheet(block: m.BlockDef) -> m.Sheet:
    """A scratch sheet holding one block's graphics (label text left out: it is rebuilt) and a
    SlotMark per slot, in slot order, with the block origin at EDIT_ORIGIN."""
    sh = m.Sheet(99, f"Block {block.name}")
    sh.width = sh.height = 12.0
    ents = [clone_entity(e) for e in block.entities if not (isinstance(e, m.Text) and e.source in LABEL_CODES)]
    for e in ents:
        translate(e, *EDIT_ORIGIN)
    marks = [m.SlotMark(round(s.x + EDIT_ORIGIN[0], 9), round(s.y + EDIT_ORIGIN[1], 9), s.terminal, m.Style("0"))
             for s in block.slots]
    sh.entities = ents + marks
    return sh


def block_from_sheet(old: m.BlockDef, sheet: m.Sheet) -> m.BlockDef:
    """The edited block: keeps the old one's data, label lines and folder; takes graphics and
    slots (in order) from the editing sheet. Existing slots keep their order, so per-part
    terminal names stay attached to the right slot."""
    marks = [e for e in leaves(sheet.entities) if isinstance(e, m.SlotMark)]
    same = len(marks) == len(old.slots)
    new = make_block(old.name, list(sheet.entities), EDIT_ORIGIN, label_lines_of(old), old.label_pos,
                     description=old.description, part_number=old.part_number, manufacturer=old.manufacturer,
                     hyperlink=old.hyperlink, tag_prefix=old.tag_prefix, increment=old.increment,
                     prefix_rule=old.prefix_rule, connector=old.connector, folder=old.folder, data=dict(old.data),
                     poles=old.poles if same else None)
    for n, o in zip(new.slots, old.slots):                       # keep where the wire number prints
        n.num_dx, n.num_dy = o.num_dx, o.num_dy
    return new


# ------------------------------------------------------------ per-part edits
def slot_name(ref: m.BlockRef, index: int, slot: m.Slot) -> str:
    """Terminal text of one slot on one placed part (its own override, else the block's)."""
    return ref.props.get(f"term{index}", slot.terminal)


def pair_numbers(count: int, first: int, step: int):
    """Terminal numbers for `count` slots taken two at a time: (first, first+1), then
    (first+step, first+step+1) ... e.g. 13/14, 23/24 or 1/2, 3/4, 5/6."""
    out = []
    for i in range(count):
        out.append(str(first + (i // 2) * step + (i % 2)))
    return out


def placed_blocks(project: m.Project):
    """One row per placed block, for pickers and reports: sheet order, then zone."""
    rows = []
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        for r in leaves(sh.entities):
            if isinstance(r, m.BlockRef):
                blk = project.blocks.get(r.block)
                rows.append({"page": pg, "zone": zone_text(sh, r.x, r.y), "tag": r.tag, "block": r.block,
                             "description": r.props.get("description", blk.description if blk else ""),
                             "ref": r})
    rows.sort(key=lambda d: (d["page"], d["zone"]))
    return rows


def duplicate_tags(project: m.Project):
    """{tag: [rows]} for tags on more than one placed block (a coil and its contacts
    share one on purpose, so this is a warning list, never an error)."""
    seen = {}
    for row in placed_blocks(project):
        if row["tag"]:
            seen.setdefault(row["tag"], []).append(row)
    return {t: v for t, v in seen.items() if len(v) > 1}


def explode_block(project, sheet, block, ref):
    """Plain drawing objects for one placed part: its graphics in place (text frozen to what
    it shows, hidden lines dropped) plus a SlotMark for each slot, so it can be edited and
    made into a block again."""
    ents = [e for e in resolved_entities(project, sheet, block, ref)
            if not (isinstance(e, m.Text) and not e.resolved)]
    for t in leaves(ents):
        if isinstance(t, m.Text):
            t.source = t.resolved
    for i, (slot, (x, y)) in enumerate(block_slots(block, ref)):
        ents.append(m.SlotMark(x, y, slot_name(ref, i, slot), m.Style("0")))
    return ents


# ------------------------------------------------------------ paste on wire
def paste_on_wire(lines, points, tol=1e-4):
    """Where two or more slot points lie on one wire, remove the part of the wire
    between them. -> [(line, [(x1, y1, x2, y2), ...])]: the pieces that remain
    (0, 1 or 2) for each affected wire."""
    ops = []
    for ln in lines:
        dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        hits = []
        for (px, py) in points:
            t = ((px - ln.x1) * dx + (py - ln.y1) * dy) / (L * L)
            dist = abs((px - ln.x1) * dy - (py - ln.y1) * dx) / L
            if dist <= tol and -tol / L <= t <= 1 + tol / L:
                hits.append((max(0.0, min(1.0, t)), (px, py)))
        if len(hits) < 2:
            continue
        hits.sort()
        (t0, p0), (t1, p1) = hits[0], hits[-1]
        if (t1 - t0) * L < 1e-6:
            continue
        pieces = []
        if t0 * L > 1e-6:
            pieces.append((ln.x1, ln.y1, p0[0], p0[1]))
        if (1 - t1) * L > 1e-6:
            pieces.append((p1[0], p1[1], ln.x2, ln.y2))
        ops.append((ln, pieces))
    return ops


def trim_single(lines, point, body, tol=1e-4):
    """A part with one slot (an off-page connector): a wire running through the slot is cut
    there, and the part of it on the side of the part's body is removed. Wires that only end
    on the slot, or run square to the body, are left alone. Same result shape as paste_on_wire."""
    ops = []
    px, py = point
    for ln in lines:
        dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        t = ((px - ln.x1) * dx + (py - ln.y1) * dy) / (L * L)
        dist = abs((px - ln.x1) * dy - (py - ln.y1) * dx) / L
        if dist > tol or not (tol / L < t < 1 - tol / L):
            continue
        side = ((body[0] - px) * dx + (body[1] - py) * dy) / L
        if side > 1e-6:
            ops.append((ln, [(ln.x1, ln.y1, px, py)]))
        elif side < -1e-6:
            ops.append((ln, [(px, py, ln.x2, ln.y2)]))
    return ops


def trim_ops(project, wires, refs):
    """Wire trimming for placed parts: parts with two or more slots remove the wire between
    their slots, one-slot parts cut the wire at the slot on the body side."""
    multi, ops = [], []
    for r in refs:
        blk = project.blocks.get(r.block)
        if blk is None:
            continue
        pts = [w for _, w in block_slots(blk, r)]
        if len(pts) == 1:
            gfx = [e for e in leaves(block_entities(blk, r)) if not isinstance(e, m.Text)]
            bb = bounds(gfx)
            if bb:
                ops += trim_single(wires, pts[0], ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2))
        else:
            multi += pts
    return ops + (paste_on_wire(wires, multi) if multi else [])


def follow_plan(project, sheet, refs, dx, dy, moved_ids=(), tol=1e-4):
    """Wires follow blocks that are being moved by (dx, dy) (call BEFORE the move).
    A wire end sitting on a slot is stretched with it: along its own direction the wire
    lengthens / shortens, and across it a short square connector keeps the wire orthogonal.
    -> (modify [(line, {fields})], add [Line], remove [Line])."""
    moved_ids = set(moved_ids)
    wires = [e for e in sheet.entities if isinstance(e, m.Line) and e.id not in moved_ids
             and project.layers.get(e.style.layer) is not None and project.layers[e.style.layer].kind == "wire"]
    mods, adds, rems, state = [], [], [], {}

    def near(a, b):
        return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol

    for ref in refs:
        blk = project.blocks.get(ref.block)
        if blk is None:
            continue
        for _, old in block_slots(blk, ref):
            for ln in wires:
                for end in (1, 2):
                    cur = state.get((ln.id, end))
                    pt = (ln.x1, ln.y1) if end == 1 else (ln.x2, ln.y2)
                    if cur is not None or not near(pt, old):
                        continue
                    other = (ln.x2, ln.y2) if end == 1 else (ln.x1, ln.y1)
                    new = (old[0] + dx, old[1] + dy)
                    conn = None
                    if abs(other[1] - pt[1]) <= tol and abs(dy) > tol:          # horizontal wire
                        new, conn = (old[0] + dx, old[1]), (old[0] + dx, old[1], old[0] + dx, old[1] + dy)
                    elif abs(other[0] - pt[0]) <= tol and abs(dx) > tol:        # vertical wire
                        new, conn = (old[0], old[1] + dy), (old[0], old[1] + dy, old[0] + dx, old[1] + dy)
                    state[(ln.id, end)] = (ln, new, conn)
    seen = {}
    for (lid, end), (ln, new, conn) in state.items():
        f = seen.setdefault(lid, (ln, {}))[1]
        if end == 1:
            f["x1"], f["y1"] = new
        else:
            f["x2"], f["y2"] = new
        if conn is not None and math.hypot(conn[2] - conn[0], conn[3] - conn[1]) > tol:
            c = m.Line(*conn, m.Style(**vars(ln.style)))
            adds.append(c)
    for lid, (ln, f) in seen.items():
        x1, y1, x2, y2 = f.get("x1", ln.x1), f.get("y1", ln.y1), f.get("x2", ln.x2), f.get("y2", ln.y2)
        if math.hypot(x2 - x1, y2 - y1) <= tol:
            rems.append(ln)
        else:
            mods.append((ln, f))
    return mods, adds, rems


def update_tags(project: m.Project) -> int:
    """Recompute automatic device tags (sheet order, then zone, then left to right),
    then make every linked part (one whose tag was picked from another block) follow
    its source. Typed tags are kept. -> number of tags changed."""
    refs = []
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        mine = [r for r in leaves(sh.entities) if isinstance(r, m.BlockRef)]
        mine.sort(key=lambda r: (zone_of(sh, r.x, r.y), r.x, -r.y))
        refs += [(sh, r) for r in mine]
    taken, changed = set(), 0
    for sh, r in refs:
        if r.props.get("tag_mode") in ("manual", "linked"):
            continue
        blk = project.blocks.get(r.block)
        if blk is None:
            continue
        tag = ""
        if blk.tag_prefix:
            base = f"{blk.tag_prefix}{sh.page:02d}{zone_text(sh, r.x, r.y)}"
            tag = base
            i = 0
            while tag in taken and i < 26:
                tag = base + chr(ord("A") + i)
                i += 1
            taken.add(tag)
        if tag != r.tag:
            r.tag = tag
            changed += 1
    by_id = {r.id: r for _, r in refs}
    for _ in range(3):                           # a link to a link settles in a few passes
        moved = False
        for _, r in refs:
            src = by_id.get(r.props.get("tag_link")) if r.props.get("tag_mode") == "linked" else None
            if src is not None and src is not r and src.tag != r.tag:
                r.tag = src.tag
                changed += 1
                moved = True
        if not moved:
            break
    return changed


def broken_links(project: m.Project):
    """[(page, ref)] linked parts whose source block no longer exists."""
    ids = {r.id for s in project.sheets.values() for r in leaves(s.entities) if isinstance(r, m.BlockRef)}
    return [(pg, r) for pg, s in sorted(project.sheets.items()) for r in leaves(s.entities)
            if isinstance(r, m.BlockRef) and r.props.get("tag_mode") == "linked"
            and r.props.get("tag_link") not in ids]


# ------------------------------------------------------------ library folders
def folder_paths(project: m.Project):
    """Every library folder (explicit ones, those blocks sit in, and their parents), sorted."""
    out = set()
    for f in list(project.block_folders) + [b.folder for b in project.blocks.values()]:
        parts = [x for x in f.split("/") if x]
        for i in range(1, len(parts) + 1):
            out.add("/".join(parts[:i]))
    return sorted(out)


def unique_block_name(project: m.Project, name: str) -> str:
    if name not in project.blocks:
        return name
    n = 2
    while f"{name} ({n})" in project.blocks:
        n += 1
    return f"{name} ({n})"


def copy_block(project: m.Project, src: str, new_name: str, folder: str = "") -> m.BlockDef:
    """Duplicate a definition under a new name in a folder. Placed parts keep using the original."""
    if new_name in project.blocks:
        raise ValueError(f"a block named {new_name!r} already exists")
    b = copy.deepcopy(project.blocks[src])
    b.name, b.folder = new_name, folder
    for e in leaves(b.entities):
        e.id = m.new_id()
    project.blocks[new_name] = b
    return b


def rename_folder(project: m.Project, old: str, new: str) -> None:
    def fix(path):
        if path == old:
            return new
        return new + path[len(old):] if path.startswith(old + "/") else path
    project.block_folders = sorted({fix(f) for f in project.block_folders} | {new})
    for b in project.blocks.values():
        b.folder = fix(b.folder)


def delete_folder(project: m.Project, path: str) -> int:
    """Remove a folder; its blocks move up one level. -> blocks moved."""
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    n = 0
    for b in project.blocks.values():
        if b.folder == path or b.folder.startswith(path + "/"):
            b.folder = (parent + b.folder[len(path):]).strip("/") if b.folder != path else parent
            n += 1
    project.block_folders = [f for f in project.block_folders if f != path and not f.startswith(path + "/")]
    return n
