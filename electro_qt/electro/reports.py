"""Wire list, wire labels and bill of materials (Qt-free, CSV)."""
from __future__ import annotations
import csv
import math
from . import model as m
from . import blocks as bk
from . import numbering as nb
from .geometry import leaves

WIRE_HEADER = ["Wire", "Layer", "Page", "Zone", "From", "To", "Other connections", "Length (in)", "Number mode"]
LABEL_HEADER = ["LabelText"]
BOM_BASE = ["Item", "Qty", "Part number", "Manufacturer", "Description", "Block", "Tags"]


def _terminals(project, sheet, nets):
    """{net.index: ["TAG:terminal", ...]} ordered left to right, top to bottom."""
    found = {n.index: [] for n in nets}
    for r in leaves(sheet.entities):
        if not isinstance(r, m.BlockRef):
            continue
        blk = project.blocks.get(r.block)
        if blk is None:
            continue
        for i, (slot, (x, y)) in enumerate(bk.block_slots(blk, r)):
            n = nb._net_at(nets, (x, y))
            if n is not None:
                term = bk.slot_name(r, i, slot)
                found[n.index].append((round(x, 3), -round(y, 3), f"{r.tag or r.block}:{term}" if term else (r.tag or r.block)))
    return {k: [t for _, _, t in sorted(v)] for k, v in found.items()}


def _net_rows(project):
    """One dict per numbered net on every sheet, pages in order."""
    rows = []
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        nets = nb.build_nets(project, sh)
        terms = _terminals(project, sh, nets)
        for n in nets:
            nums = [l.number for l in n.lines if l.number is not None and l.number.value]
            if not nums:
                continue
            rows.append({"wire": nums[0].value, "mode": nums[0].mode, "layer": n.layer, "page": pg,
                         "zone": bk.zone_text(sh, *n.anchor), "terms": terms[n.index], "anchor": n.anchor,
                         "length": sum(math.hypot(l.x2 - l.x1, l.y2 - l.y1) for l in n.lines)})
    rows.sort(key=lambda r: (r["page"], r["zone"], r["wire"]))
    return rows


def wire_list(project):
    out = []
    for r in _net_rows(project):
        t = r["terms"]
        out.append([r["wire"], r["layer"], f"{r['page']:02d}", r["zone"], t[0] if t else "",
                    t[1] if len(t) > 1 else "", " ; ".join(t[2:]), f"{r['length']:.2f}", r["mode"]])
    return out


def wire_labels(project):
    """Label printer file: one column, every wire number twice (one label for each end)."""
    out = []
    for r in _net_rows(project):
        out += [[r["wire"]], [r["wire"]]]
    return out


def bom(project):
    """-> (header, rows). Placed blocks grouped by part number + manufacturer + description,
    using each part's own overrides. Extra block data fields become extra columns."""
    groups = {}
    keys = []
    for pg in sorted(project.sheets):
        for r in leaves(project.sheets[pg].entities):
            if not isinstance(r, m.BlockRef):
                continue
            blk = project.blocks.get(r.block)
            if blk is None:
                continue
            pn = r.props.get("part_number", blk.part_number)
            mf = r.props.get("manufacturer", blk.manufacturer)
            ds = r.props.get("description", blk.description)
            g = groups.setdefault((pn, mf, ds, blk.name), {"tags": [], "data": dict(blk.data)})
            g["tags"].append(r.tag)
            for k in blk.data:
                if k not in keys:
                    keys.append(k)
    header = BOM_BASE + keys
    rows = []
    for i, ((pn, mf, ds, name), g) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0][0] == "", kv[0][0], kv[0][3])), 1):
        tags = sorted(t for t in g["tags"] if t)
        rows.append([i, len(g["tags"]), pn, mf, ds, name, ", ".join(tags)] + [g["data"].get(k, "") for k in keys])
    return header, rows


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:     # BOM so Excel reads UTF-8
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
