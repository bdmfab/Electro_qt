"""Rule check (Qt-free): things that are probably mistakes in a project. Nothing is changed."""
from __future__ import annotations
from dataclasses import dataclass
from . import model as m
from . import blocks as bk
from . import numbering as nb
from .geometry import leaves
from .templates import zone_of

CATEGORIES = ["Duplicate tag", "Missing tag", "Unconnected slot", "Wire not reached", "Duplicate wire number",
              "Broken tag link", "Connector without partner"]


@dataclass
class Issue:
    category: str
    page: int
    zone: str
    x: float
    y: float
    message: str


def _zone(project, page, x, y):
    return bk.zone_text(project.sheets[page], x, y)


def check(project: m.Project) -> list:
    """-> [Issue] in sheet order."""
    out = []
    rows = bk.placed_blocks(project)
    by_id = {r["ref"].id: r for r in rows}

    # ---- duplicate / missing tags
    seen = {}
    for r in rows:
        blk = project.blocks.get(r["block"])
        if blk is None or blk.connector:
            continue
        ref = r["ref"]
        if r["tag"]:
            seen.setdefault(r["tag"], []).append(r)
        elif "tag" in bk.label_lines_of(blk) or blk.tag_prefix:
            out.append(Issue("Missing tag", r["page"], r["zone"], ref.x, ref.y,
                             f"{r['block']} has no tag (Update device tags)"))
    for tag, group in seen.items():
        if len(group) < 2:
            continue
        ids = {g["ref"].id for g in group}
        # a coil and its contacts share a tag on purpose: the others are linked to a member of the group
        owners = [g for g in group if not (g["ref"].props.get("tag_mode") == "linked"
                                           and g["ref"].props.get("tag_link") in ids)]
        if len(owners) > 1:
            where = ", ".join(f"{g['page']:02d}/{g['zone']}" for g in owners)
            for g in owners:
                out.append(Issue("Duplicate tag", g["page"], g["zone"], g["ref"].x, g["ref"].y,
                                 f"Tag {tag} is also used by {len(owners) - 1} other part(s) ({where})"))

    # ---- unconnected slots
    for pg in sorted(project.sheets):
        sh = project.sheets[pg]
        nets = nb.build_nets(project, sh)
        for r in leaves(sh.entities):
            if not isinstance(r, m.BlockRef):
                continue
            blk = project.blocks.get(r.block)
            if blk is None:
                continue
            for i, (slot, pt) in enumerate(bk.block_slots(blk, r)):
                if nb._net_at(nets, pt) is None:
                    term = bk.slot_name(r, i, slot)
                    out.append(Issue("Unconnected slot", pg, _zone(project, pg, *pt), pt[0], pt[1],
                                     f"{r.tag or r.block}{':' + term if term else ''} has no wire on its slot"))

    # ---- wire numbers
    rep = nb.update(project)
    for pg, (x, y) in rep.unreached:
        out.append(Issue("Wire not reached", pg, _zone(project, pg, x, y), x, y,
                         "No marked wire reaches this wire (Mark wire, then Update wire numbers)"))
    for val, members in rep.duplicates:
        for pg, net in members:
            out.append(Issue("Duplicate wire number", pg, _zone(project, pg, *net.anchor), net.anchor[0], net.anchor[1],
                             f"Wire number {val} is used by {len(members)} wires (apply a goto or change one)"))

    # ---- tag links
    for pg, r in bk.broken_links(project):
        out.append(Issue("Broken tag link", pg, _zone(project, pg, r.x, r.y), r.x, r.y,
                         f"{r.block} {r.tag} takes its tag from a part that no longer exists"))

    # ---- off-page connectors with one end only
    names = {}
    for r in rows:
        blk = project.blocks.get(r["block"])
        if blk is not None and blk.connector and r["tag"]:
            names.setdefault(r["tag"], []).append(r)
    for name, group in names.items():
        if len(group) == 1:
            g = group[0]
            out.append(Issue("Connector without partner", g["page"], g["zone"], g["ref"].x, g["ref"].y,
                             f"Connector {name} appears only once"))
    out.sort(key=lambda i: (i.page, CATEGORIES.index(i.category), i.y * -1, i.x))
    return out


HEADER = ["Category", "Sheet", "Zone", "Message"]


def as_rows(issues):
    return [[i.category, f"{i.page:02d}", i.zone, i.message] for i in issues]
