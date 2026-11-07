"""Wire numbering (Qt-free).

Nets: wire lines on one layer that touch (end to end, end on the side of another line,
or crossing at a solid dot) are electrically one wire and share a number.
Blocks join nets: slots are taken two at a time (1-2, 3-4 ...), so a pole passes a run
from one net to the next. Numbering walks out from each 'Mark wire' origin; passing a
block whose increment is +1 advances the incident digit, other blocks and dots do not.

Layer scheme variables: <page> <zone> <col> <incident> <g_incident> <phase_incident> <L|T> <phase>
  <page>/<zone>  two digits; taken from the net's LEFT end (left to right on the page)
  <incident>     start digit (from the mark) + increment blocks passed
  <phase_incident> number shared by a set of parallel phase wires (L1 L2 L3), counted
                 1, 2, 3 ... along the circuit: down each branch, top branch first
  <g_incident>   global counter 1, 2, 3 ... over every auto-numbered wire using it, page by
                 page, left to right then top to bottom; needs no mark
  <L|T> etc.     letter rules (Project.prefix_rules): the true text when a block with that
                 rule touches the net, else the false text (default: motor -> T, else L)
  <phase>        the layer's phase digit (L1 -> 1); PE layers are never numbered
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from . import model as m
from .blocks import block_slots
from .geometry import leaves
from .templates import zone_of

TOL = 1e-4
DEFAULT_DC = "<page><zone><incident>"
DEFAULT_AC = "<incident><L|T><phase>"


# ---------------------------------------------------------------- geometry helpers
def _on_segment(p, ln, tol=TOL):
    dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(p[0] - ln.x1, p[1] - ln.y1) <= tol
    t = ((p[0] - ln.x1) * dx + (p[1] - ln.y1) * dy) / L2
    if t < -tol or t > 1 + tol:
        return False
    return abs((p[0] - ln.x1) * dy - (p[1] - ln.y1) * dx) / math.sqrt(L2) <= tol


def _interior(p, ln, tol=TOL):
    return _on_segment(p, ln, tol) and min(math.hypot(p[0] - ln.x1, p[1] - ln.y1),
                                           math.hypot(p[0] - ln.x2, p[1] - ln.y2)) > tol


def _cross_point(a, b):
    """Intersection of two segments (or None); parallel lines never cross."""
    d1x, d1y, d2x, d2y = a.x2 - a.x1, a.y2 - a.y1, b.x2 - b.x1, b.y2 - b.y1
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-12:
        return None
    t = ((b.x1 - a.x1) * d2y - (b.y1 - a.y1) * d2x) / den
    u = ((b.x1 - a.x1) * d1y - (b.y1 - a.y1) * d1x) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return a.x1 + t * d1x, a.y1 + t * d1y
    return None


# ---------------------------------------------------------------- nets
@dataclass
class Net:
    index: int
    layer: str
    lines: list
    anchor: tuple = (0.0, 0.0)           # left-most (then top-most) end point
    blocks: list = field(default_factory=list)      # BlockDefs touching this net
    origin: object = None                # the marked Line, if any
    page: int = 0
    numbered: bool = False
    fixed: bool = False                  # typed / locked / ignored number
    base: tuple = None                   # anchor of the marked net this number was counted from
    incident: int = None
    pinc: int = None                     # <phase_incident>
    value: str = ""
    mode: str = "auto"                   # auto | override | locked (from the lines)


def _numbered_layer(project, name):
    lay = project.layers.get(name)
    return lay is not None and lay.kind == "wire" and lay.numbered and lay.phase.upper() != "PE"


def _wire_layer(project, name):
    lay = project.layers.get(name)
    return lay is not None and lay.kind == "wire"


def build_nets(project, sheet, include=()):
    """Nets of the numbered layers, plus wires on any wire layer that carry a typed / locked /
    ignored number (so PE and other un-numbered wires can be numbered by hand). `include` =
    ids of lines to take in regardless (used when a number is being set for the first time)."""
    include = set(include)
    lines = [e for e in sheet.entities if isinstance(e, m.Line) and
             (_numbered_layer(project, e.style.layer)
              or (_wire_layer(project, e.style.layer) and
                  (e.id in include or (e.number is not None and e.number.mode != "auto"))))]
    dots = [e for e in sheet.entities if isinstance(e, m.Circle) and e.filled]
    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i, a in enumerate(lines):
        for j in range(i + 1, len(lines)):
            b = lines[j]
            if a.style.layer != b.style.layer:
                continue
            ends_a, ends_b = ((a.x1, a.y1), (a.x2, a.y2)), ((b.x1, b.y1), (b.x2, b.y2))
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= TOL for p in ends_a for q in ends_b) \
                    or any(_on_segment(p, b) for p in ends_a) or any(_on_segment(q, a) for q in ends_b):
                union(i, j)
                continue
            x = _cross_point(a, b)
            if x is not None and any(math.hypot(d.cx - x[0], d.cy - x[1]) <= max(d.r, TOL) + TOL for d in dots):
                union(i, j)                                 # a crossing joined by a solid dot
    groups = {}
    for i, ln in enumerate(lines):
        groups.setdefault(find(i), []).append(ln)
    nets = []
    for g in groups.values():
        pts = [(l.x1, l.y1) for l in g] + [(l.x2, l.y2) for l in g]
        anchor = min(pts, key=lambda p: (round(p[0], 4), -p[1]))
        net = Net(len(nets), g[0].style.layer, g, anchor)
        net.origin = next((l for l in g if l.mark != ""), None)
        nets.append(net)
    nets.sort(key=lambda n: (round(n.anchor[0], 3), -n.anchor[1]))
    for i, n in enumerate(nets):
        n.index = i
    return nets


def _net_at(nets, p):
    for n in nets:
        if any(_on_segment(p, l) for l in n.lines):
            return n
    return None


def block_links(project, sheet, nets):
    """[(netA, netB, BlockDef)] for each pole (slot pair) that lands on nets; also records
    which blocks touch each net."""
    edges = []
    for r in sheet.entities:
        if not isinstance(r, m.BlockRef):
            continue
        blk = project.blocks.get(r.block)
        if blk is None:
            continue
        hits = [_net_at(nets, w) for _, w in block_slots(blk, r)]
        for n in hits:
            if n is not None and blk not in n.blocks:
                n.blocks.append(blk)
        for k in range(0, len(hits) - 1, 2):
            if hits[k] is not None and hits[k + 1] is not None:
                edges.append((hits[k], hits[k + 1], blk))
    return edges


def phase_sets(project, sheet, nets, counter=0):
    """Number the phase sets of one sheet -> ({net.index: number}, new counter).
    A set is the group of nets that run in parallel: the same side of one block (L1/L2/L3
    in, or out), nets drawn together as a multiline bundle, and both sides of a block that
    does not increment. Sets are numbered depth-first along the circuit from the marked wire
    (or the top-left set): after an incrementing block comes the next number, a branch is
    finished before the next one starts (top branch first)."""
    parent = list(range(len(nets)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    by_line = {id(l): n.index for n in nets for l in n.lines}
    for b in sheet.bundles:
        ids = [by_line[id(e)] for e in sheet.entities if isinstance(e, m.Line) and e.id in b.members and id(e) in by_line]
        for x in ids[1:]:
            union(ids[0], x)
    links = []                                       # (ref, in-nets, out-nets, increments)
    for r in sheet.entities:
        if not isinstance(r, m.BlockRef):
            continue
        blk = project.blocks.get(r.block)
        if blk is None:
            continue
        hits = [_net_at(nets, w) for _, w in block_slots(blk, r)]
        ins = [h.index for h in hits[0::2] if h is not None]
        outs = [h.index for h in hits[1::2] if h is not None]
        for side in (ins, outs):
            for x in side[1:]:
                union(side[0], x)
        if blk.increment == 1:
            if ins and outs:
                links.append((r, ins[0], outs[0]))
        else:
            for x in ins + outs:
                union((ins + outs)[0], x)
    sets = {}
    for n in nets:
        sets.setdefault(find(n.index), []).append(n)
    key = lambda root: min((round(n.anchor[0], 3), -n.anchor[1]) for n in sets[root])
    adj = {root: [] for root in sets}
    for r, a, b in links:
        ra, rb = find(a), find(b)
        if ra != rb:
            adj[ra].append((-r.y, r.x, rb)); adj[rb].append((-r.y, r.x, ra))
    number = {}
    marked = [root for root in sorted(sets, key=key) if any(n.origin is not None for n in sets[root])]
    order = marked + [root for root in sorted(sets, key=key) if root not in marked]

    def visit(root, start=None):
        nonlocal counter
        stack = [root]
        while stack:
            cur = stack.pop()
            if cur in number:
                continue
            if start is not None and cur == root:
                counter = start
            else:
                counter += 1
            number[cur] = counter
            for _, _, nxt in sorted(adj[cur], reverse=True):      # reversed so the top branch pops first
                if nxt not in number:
                    stack.append(nxt)

    for root in order:
        if root in number:
            continue
        start = None
        for n in sets[root]:
            if n.origin is not None:
                try:
                    start = int(n.origin.mark)
                except ValueError:
                    pass
        visit(root, start)
    return {n.index: number[find(n.index)] for n in nets}, counter


# ---------------------------------------------------------------- formatting
def phase_text(layer: m.Layer) -> str:
    ph = layer.phase.strip()
    return ph[1:] if len(ph) == 2 and ph[0].upper() == "L" and ph[1].isdigit() else ph


def format_number(scheme, project, sheet, net, incident, g_incident=0, p_incident=0):
    layer = project.layers[net.layer]
    scheme = scheme or DEFAULT_DC
    zone = zone_of(sheet, *(net.base or net.anchor))     # zone of the marked wire the count started from
    out = (scheme.replace("<page>", f"{sheet.page:02d}").replace("<zone>", f"{zone:02d}")
           .replace("<col>", str(zone // 25 + 1)).replace("<phase_incident>", str(p_incident)).replace("<g_incident>", str(g_incident)).replace("<incident>", str(incident))
           .replace("<phase>", phase_text(layer)))
    touching = {b.prefix_rule.strip().lower() for b in net.blocks if b.prefix_rule.strip()}
    done = set()
    for r in project.prefix_rules:                       # letter rules: pattern -> true / false text
        if r.pattern in done or r.pattern not in out:
            continue
        same = [x for x in project.prefix_rules if x.pattern == r.pattern]
        hit = next((x for x in same if x.name.strip().lower() in touching), None)
        out = out.replace(r.pattern, hit.if_true if hit else same[0].if_false)
        done.add(r.pattern)
    return out.lstrip("0") if project.lead_zero_suppress else out


def default_start(project, layer_name) -> int:
    lay = project.layers.get(layer_name)
    pats = {r.pattern for r in project.prefix_rules} | {"<L|T>"}
    return 1 if lay is not None and any(p in (lay.scheme or "") for p in pats) else 0


# ---------------------------------------------------------------- the update
@dataclass
class Report:
    changes: dict = field(default_factory=dict)     # sheet page -> [(line, WireNumber)]
    warnings: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)   # [(number, [(page, Net), ...])] genuine repeats
    unreached: list = field(default_factory=list)    # [(page, (x, y))] wires no marked wire reaches
    numbered: int = 0
    nets: int = 0


def connector_groups(project, sheets_nets, names=None):
    """[[Net, ...]] nets joined through off-page connectors (blocks flagged `connector` that
    share a tag), page order. sheets_nets = {page: nets}."""
    byname = {}
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        for r in sh.entities:
            if not isinstance(r, m.BlockRef):
                continue
            blk = project.blocks.get(r.block)
            if blk is None or not blk.connector or not r.tag or not blk.slots:
                continue
            n = _net_at(sheets_nets[pg], block_slots(blk, r)[0][1])
            if n is not None and n not in byname.setdefault(r.tag, []):
                byname[r.tag].append(n)
    out = []
    for tag, g in byname.items():
        if len(g) > 1:
            out.append(g)
            if names is not None:
                names.append(tag)
    return out


def update(project) -> Report:
    """Compute every wire number. Does not modify the project: Report.changes lists the
    new WireNumber for each line that needs one (auto lines only). Wires that continue on
    another sheet through off-page connectors (same tag) are one wire: the count carries
    across and both ends get the same number."""
    rep = Report()
    pages = sorted(project.sheets)
    data = {}                                           # page -> (nets, edges)
    for pg in pages:
        nets = build_nets(project, project.sheets[pg])
        for n in nets:
            n.page = pg
        data[pg] = (nets, block_links(project, project.sheets[pg], nets))
    group_names = []
    groups = connector_groups(project, {pg: data[pg][0] for pg in pages}, group_names)
    group_of = {id(n): gi for gi, g in enumerate(groups) for n in g}

    # ---- incident counting, across sheets
    adj = {id(n): [] for pg in pages for n in data[pg][0]}
    for pg in pages:
        for k, (a, b, blk) in enumerate(data[pg][1]):
            step = 1 if blk.increment == 1 else 0
            adj[id(a)].append((b, step, (pg, k))); adj[id(b)].append((a, step, (pg, k)))
    for gi, g in enumerate(groups):
        for k, (a, b) in enumerate(zip(g, g[1:])):
            adj[id(a)].append((b, 0, ("c", gi, k))); adj[id(b)].append((a, 0, ("c", gi, k)))
    used, queue = set(), []
    for pg in pages:
        for n in data[pg][0]:
            if n.origin is not None:
                try:
                    n.incident = int(n.origin.mark)
                except ValueError:
                    n.incident = default_start(project, n.layer)
                n.base = n.anchor
                queue.append(n)
    while queue:
        n = queue.pop(0)
        for nb, step, k in adj[id(n)]:
            if k in used:                       # each block pole is crossed once, outward
                continue
            used.add(k)
            inc = n.incident + step
            if nb.incident is None:
                nb.incident = inc
                nb.base = n.base
                queue.append(nb)
            elif nb.incident != inc:
                rep.warnings.append(f"Sheet {nb.page:02d}: two routes give different numbers near x={nb.anchor[0]:.2f} "
                                    f"(kept {nb.incident}, other route {inc})")

    # ---- values
    g_count = p_count = 0
    first_value = {}                                    # connector group -> value of its first net
    uses_phase = any("<phase_incident>" in (l.scheme or "") for l in project.layers.values())
    for pg in pages:
        sh = project.sheets[pg]
        nets = data[pg][0]
        if uses_phase:
            pm, p_count = phase_sets(project, sh, nets, p_count)
            for n in nets:
                n.pinc = pm[n.index]
        for n in nets:
            rep.nets += 1
            scheme = project.layers[n.layer].scheme or DEFAULT_DC
            glob = "<g_incident>" in scheme or "<phase_incident>" in scheme
            needs_inc = "<incident>" in scheme
            modes = [l.number for l in n.lines if l.number is not None and l.number.mode != "auto"]
            gid = group_of.get(id(n))
            n.numbered = True
            if modes:                                    # typed / locked: left alone, shared by the net
                n.mode, n.value = modes[0].mode, modes[0].value
                n.fixed = True
            elif gid is not None and first_value.get(gid):
                n.value = first_value[gid]               # the other end of a connector: same wire
            elif n.incident is not None or (glob and not needs_inc):
                if n.incident is not None and n.incident > 9 and needs_inc:
                    rep.warnings.append(f"Sheet {pg:02d}: incident {n.incident} needs more than one digit "
                                        f"(zone {zone_of(sh, *n.anchor):02d})")
                if "<g_incident>" in scheme:
                    g_count += 1
                n.value = format_number(scheme, project, sh, n, n.incident if n.incident is not None else 0, g_count, n.pinc or 0)
            else:
                rep.warnings.append(f"Sheet {pg:02d}: a wire near x={n.anchor[0]:.2f}, "
                                    f"zone {zone_of(sh, *n.anchor):02d} is not reached from any marked wire")
                rep.unreached.append((pg, n.anchor))
                n.numbered = False
                continue
            if gid is not None and n.value and (gid not in first_value or n.fixed):
                first_value[gid] = n.value               # a typed number wins over the first one
    # a typed number on one end of a connector wins on the others
    for gi, g in enumerate(groups):
        val = first_value.get(gi)
        for n in g:
            if val and n.numbered and not n.fixed and n.value != val:
                n.value = val

    # ---- changes, duplicates
    seen = {}                                           # number -> [(page, net)]
    for pg in pages:
        for n in data[pg][0]:
            if not n.numbered:
                continue
            if n.fixed:
                new = [(l, m.WireNumber(n.mode, n.value)) for l in n.lines
                       if l.number is None or (l.number.mode, l.number.value) != (n.mode, n.value)]
            else:
                new = [(l, m.WireNumber("auto", n.value)) for l in n.lines
                       if l.number is None or (l.number.mode, l.number.value) != ("auto", n.value)]
            if new:
                rep.changes.setdefault(pg, []).extend(new)
            rep.numbered += 1
            seen.setdefault(n.value, []).append((pg, n))
    group_names_by_id = {gi: group_names[gi] for gi in range(len(groups))}
    for val, lst in sorted(seen.items()):
        distinct = {group_of.get(id(n), id(n)) for _, n in lst}
        if all(n.fixed and n.mode == "goto" for _, n in lst):
            continue                                     # (old files) wires tied with a goto-mode number
        tied = {g for g in distinct if g in group_names_by_id and goto_names(group_names_by_id[g])[0] == val
                and goto_names(group_names_by_id[g])[1]}
        distinct -= tied                                 # sets tied by a From / To named NUMBER-k are not duplicates
        lst = [(pg, n) for pg, n in lst if group_of.get(id(n), id(n)) not in tied]
        if len(distinct) > 1 and val:
            rep.duplicates.append((val, sorted(lst, key=lambda t: (t[0], t[1].anchor[0], -t[1].anchor[1]))))
            where = ", ".join(f"{pg:02d}/{zone_of(project.sheets[pg], *n.anchor):02d}" for pg, n in lst)
            rep.warnings.append(f"Number {val} is used more than once (sheet/zone: {where})")
    return rep


def apply(project, report: Report) -> int:
    n = 0
    for pg, lst in report.changes.items():
        for line, num in lst:
            line.number = num
            n += 1
    return n


# ---------------------------------------------------------------- gotos
def _net_value(net):
    nums = [l.number for l in net.lines if l.number is not None and l.number.value]
    return (nums[0].value, nums[0].mode) if nums else ("", "auto")


def numbered_nets(project):
    """[(page, Net, value)] for every wire that currently carries a number, pages in order."""
    out = []
    for pg in sorted(project.sheets):
        for n in build_nets(project, project.sheets[pg]):
            v, _ = _net_value(n)
            if v:
                out.append((pg, n, v))
    return out


def goto_names(value, taken_values=()):
    """Split 'BASE-2' -> ('BASE', 2); a plain number -> (number, 0)."""
    mt = re.match(r"^(.*)-(\d+)$", value)
    return (mt.group(1), int(mt.group(2))) if mt else (value, 0)


def next_connector_name(project, base, taken=()):
    """BASE-k for the next free set: after the highest BASE-k on a placed connector block
    (or already handed out in `taken`)."""
    ks = [goto_names(t)[1] for t in taken if goto_names(t)[0] == base]
    for sh in project.sheets.values():
        for e in leaves(sh.entities):
            if isinstance(e, m.BlockRef):
                blk = project.blocks.get(e.block)
                if blk is not None and blk.connector and goto_names(e.tag)[0] == base:
                    ks.append(goto_names(e.tag)[1])
    return f"{base}-{max(ks + [0]) + 1}"


def free_ends(project, page, net, tol=1e-4):
    """[(point, outward_direction)] ends of a wire that touch nothing: no other line of the net
    and no slot of a placed part. Outward points away from the wire."""
    from . import blocks as bk
    sh = project.sheets[page]
    taken = []
    for e in leaves(sh.entities):
        if isinstance(e, m.BlockRef):
            blk = project.blocks.get(e.block)
            if blk is not None:
                taken += [w for _, w in bk.block_slots(blk, e)]
    ends = []
    for l in net.lines:
        ends.append(((l.x1, l.y1), (l.x2, l.y2)))
        ends.append(((l.x2, l.y2), (l.x1, l.y1)))
    out = []
    for i, (p, q) in enumerate(ends):
        if any(j != i and math.hypot(p[0] - ends[j][0][0], p[1] - ends[j][0][1]) <= tol for j in range(len(ends))):
            continue
        if any(math.hypot(p[0] - t[0], p[1] - t[1]) <= tol for t in taken):
            continue
        L = math.hypot(p[0] - q[0], p[1] - q[1])
        if L > 1e-9:
            out.append((p, ((p[0] - q[0]) / L, (p[1] - q[1]) / L)))
    return out


def goto_connectors(project, a, b, name):
    """Place a From connector on wire a (skipped when a is None: the wire already has one) and a To
    connector on wire b (each a (page, Net)), both called `name`, at a free end of the wire: From
    where the wire leaves to the right, To where it arrives from the left, turned to suit.
    -> ([(page, 'From'|'To', (x, y), rotation, name)], [problems])."""
    out, bad = [], []
    for kind, w in (("From", a), ("To", b)):
        if w is None:
            continue
        pg, net = w
        ends = free_ends(project, pg, net)
        if not ends:
            bad.append(f"Sheet {pg:02d}: the wire near x={net.anchor[0]:.2f} has no free end for a {kind}")
            continue
        sg = 1 if kind == "From" else -1
        p, d = max(ends, key=lambda e: (round(sg * e[1][0], 3), round(sg * e[0][0], 3)))
        ang = math.degrees(math.atan2(sg * d[1], sg * d[0]))
        out.append((pg, kind, p, round(ang, 3) % 360.0, name))
    return out, bad


def net_from_name(project, page, net, tol=1e-4):
    """Name of the From connector already sitting on this wire, or ''."""
    sh = project.sheets[page]
    for e in leaves(sh.entities):
        if isinstance(e, m.BlockRef) and e.tag and e.block == "From":
            blk = project.blocks.get(e.block)
            if blk is None or not blk.slots:
                continue
            pt = block_slots(blk, e)[0][1]
            if any(_on_segment(pt, l, tol) for l in net.lines):
                return e.tag
    return ""


def goto_plan(project, to_line_ids, from_line_id):
    """Tie two wires with a goto from the wire menu. The selected wire is the To end, the picked
    wire the From end. One From can go to several Tos: when the picked wire already has a From, its
    name is reused and only a To is added. -> (name, from_net or None, to_net, value) or None when
    the picked wire has no number."""
    this = other = None
    this_ids = set(to_line_ids)
    for pg in sorted(project.sheets):
        for n in build_nets(project, project.sheets[pg], include=this_ids | {from_line_id}):
            ids = {l.id for l in n.lines}
            if ids & this_ids and this is None:
                this = (pg, n)
            if from_line_id in ids and other is None:
                other = (pg, n)
    if this is None or other is None or this[1] is other[1]:
        return None
    val, _ = _net_value(other[1])
    if not val:
        return None
    have = net_from_name(project, *other)
    if have:
        return have, None, this, val
    return next_connector_name(project, val), other, this, val


def goto_duplicates(project, duplicates):
    """Resolve the duplicates a report found. The wires sharing a number are taken two at a time
    (sheet / position order): the first pair becomes a set NUMBER-1, the next NUMBER-2 ... the
    first wire of a pair gets the From, the second the To. A wire left over is skipped.
    -> [(name, (page, Net), (page, Net))]."""
    plan, taken = [], []
    for val, members in duplicates:
        for i in range(0, len(members) - 1, 2):
            name = next_connector_name(project, val, taken)
            taken.append(name)
            plan.append((name, members[i], members[i + 1]))
    return plan


# ---------------------------------------------------------------- label placement
def label_spec(net: Net):
    """(x, y, rotation, text) for the single label of a net: beside the middle of its
    longest line, above a horizontal one, left of a vertical one (reading upward)."""
    ln = max(net.lines, key=lambda l: math.hypot(l.x2 - l.x1, l.y2 - l.y1))
    mx, my = (ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2
    if abs(ln.x2 - ln.x1) >= abs(ln.y2 - ln.y1):
        return mx, my + 0.05, 0.0
    return mx - 0.06, my, 90.0


def net_labels(project, sheet):
    """[(x, y, rotation, text, mode)] for every numbered net on the sheet."""
    return [t[:5] for t in net_labels_full(project, sheet)]


def net_labels_full(project, sheet):
    """Like net_labels, with the net's lines as a sixth item (to select the wire from its label)."""
    out = []
    for n in build_nets(project, sheet):
        nums = [l.number for l in n.lines if l.number is not None and l.number.value]
        if not nums:
            continue
        x, y, rot = label_spec(n)
        out.append((x, y, rot, nums[0].value, nums[0].mode, n.lines))
    return out
