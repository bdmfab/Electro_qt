"""Project bundle (zip of XML) save/load. Layout per spec section 15."""
from __future__ import annotations
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import fields
from . import model as m

_NUM = {float: float, int: int, bool: lambda s: s == "1", str: str}


def _fmt(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return repr(v)
    return str(v)


# ---- style / entity -------------------------------------------------------
def _style_attrs(el, st: m.Style):
    el.set("layer", st.layer)
    if st.color is not None:
        el.set("color", str(st.color))
    if st.width:
        el.set("width", _fmt(st.width))
    if st.linetype != "continuous":
        el.set("linetype", st.linetype)


def _style_from(el) -> m.Style:
    c = el.get("color")
    return m.Style(el.get("layer", "0"), int(c) if c is not None else None,
                   float(el.get("width", "0")), el.get("linetype", "continuous"))


_SKIP = {"style", "number", "props", "source", "entities", "slots", "data", "children"}


def ent_to_xml(e) -> ET.Element:
    el = ET.Element(e.TAG)
    for f in fields(e):
        if f.name in _SKIP:
            continue
        v = getattr(e, f.name)
        if isinstance(v, str) and v == "" and f.name not in ("id",):
            continue
        el.set(f.name, _fmt(v))
    _style_attrs(el, e.style)
    if isinstance(e, m.Line) and e.number:
        ET.SubElement(el, "number", mode=e.number.mode, value=e.number.value)
    if isinstance(e, m.Text):
        ET.SubElement(el, "source").text = e.source
    if isinstance(e, m.BlockRef):
        for k, v in e.props.items():
            ET.SubElement(el, "prop", name=k, value=str(v))
    if isinstance(e, m.Group):
        for c in e.children:
            el.append(ent_to_xml(c))
    return el


def ent_from_xml(el):
    cls = m.ENTITY_TYPES[el.tag]
    kw = {}
    for f in fields(cls):
        if f.name in _SKIP or el.get(f.name) is None:
            continue
        t = f.type if not isinstance(f.type, str) else {
            "float": float, "str": str, "bool": bool, "int": int}.get(f.type, str)
        kw[f.name] = _NUM.get(t, str)(el.get(f.name))
    e = cls(**{**_required(cls, el), **kw}, style=_style_from(el))
    n = el.find("number")
    if n is not None:
        e.number = m.WireNumber(n.get("mode"), n.get("value", ""))
    s = el.find("source")
    if s is not None:
        e.source = s.text or ""
    if cls is m.BlockRef:
        for p in el.findall("prop"):
            e.props[p.get("name")] = p.get("value")
    if cls is m.Group:
        for sub in el:
            if sub.tag in m.ENTITY_TYPES:
                e.children.append(ent_from_xml(sub))
    return e


def _required(cls, el):
    # Text.source is required positional; give a placeholder, filled after.
    if cls is m.Text:
        return {"source": ""}
    return {"children": []} if cls is m.Group else {}


# ---- sheet ----------------------------------------------------------------
def sheet_to_xml(s: m.Sheet) -> ET.Element:
    root = ET.Element("sheet", schema_version=str(m.SCHEMA_VERSION),
                      page=m.page_str(s.page), title=s.title,
                      zones=str(s.zone_count), row_pitch=_fmt(s.row_pitch),
                      units=s.units, grid_divisions=str(s.grid_divisions),
                      width=_fmt(s.width), height=_fmt(s.height),
                      zone0_y=_fmt(s.zone0_y), grid_x0=_fmt(s.grid_x0))
    if s.col_split_x is not None:
        root.set("col_split_x", _fmt(s.col_split_x))
    if s.logo_box:
        root.set("logo_box", ",".join(repr(float(v)) for v in s.logo_box))
    for i, t in enumerate(s.title_lines):
        ET.SubElement(root, "title_line", n=str(i + 1), text=t)
    fr = ET.SubElement(root, "frame")
    for e in s.frame:
        fr.append(ent_to_xml(e))
    ents = ET.SubElement(root, "entities")
    for e in s.entities:
        ents.append(ent_to_xml(e))
    for b in s.bundles:
        be = ET.SubElement(root, "bundle", id=b.id, preset=b.preset,
                           spacing=_fmt(b.spacing))
        for mid in b.members:
            ET.SubElement(be, "member", id=mid)
    for g in s.gotos:
        ge = ET.SubElement(root, "goto", id=g.id, x=_fmt(g.x), y=_fmt(g.y))
        for num, page in g.targets:
            ET.SubElement(ge, "target", wire=num, page=m.page_str(page))
    return root


def sheet_from_xml(root: ET.Element) -> m.Sheet:
    s = m.Sheet(int(root.get("page")), root.get("title", ""),
                int(root.get("zones", "25")), float(root.get("row_pitch", "0.35")),
                root.get("units", "in"), int(root.get("grid_divisions", "1")),
                width=float(root.get("width", "17")), height=float(root.get("height", "11")),
                zone0_y=float(root.get("zone0_y", "9.45")), grid_x0=float(root.get("grid_x0", "0")),
                col_split_x=float(root.get("col_split_x")) if root.get("col_split_x") else None,
                logo_box=tuple(float(v) for v in root.get("logo_box").split(",")) if root.get("logo_box") else None)
    lines = {int(t.get("n")): t.get("text", "") for t in root.findall("title_line")}
    s.title_lines = [lines.get(i, "") for i in range(1, 5)]
    fr = root.find("frame")
    if fr is not None:
        for el in fr:
            s.frame.append(ent_from_xml(el))
    for el in root.find("entities"):
        s.entities.append(ent_from_xml(el))
    for be in root.findall("bundle"):
        s.bundles.append(m.Bundle([x.get("id") for x in be.findall("member")],
                                  be.get("preset"), float(be.get("spacing")),
                                  be.get("id")))
    for ge in root.findall("goto"):
        s.gotos.append(m.Goto(float(ge.get("x")), float(ge.get("y")),
                              [(t.get("wire"), int(t.get("page")))
                               for t in ge.findall("target")], ge.get("id")))
    return s


# ---- block ----------------------------------------------------------------
def _layer_to_xml(parent, l: m.Layer, tag="layer"):
    return ET.SubElement(parent, tag, name=l.name, color=str(l.color), kind=l.kind,
                         numbered=_fmt(l.numbered), scheme=l.scheme,
                         linetype=l.linetype, lineweight=_fmt(l.lineweight), phase=l.phase)


def _layer_from_xml(l) -> m.Layer:
    return m.Layer(l.get("name"), int(l.get("color")), l.get("kind"), l.get("numbered") == "1",
                   l.get("scheme", ""), l.get("linetype", "continuous"),
                   float(l.get("lineweight", "0")), l.get("phase", ""))


def block_to_xml(b: m.BlockDef) -> ET.Element:
    el = ET.Element("block", name=b.name, description=b.description,
                    part_number=b.part_number, tag_prefix=b.tag_prefix,
                    hyperlink=b.hyperlink, manufacturer=b.manufacturer,
                    increment=str(b.increment), connector=str(b.connector), prefix_rule=b.prefix_rule,
                    poles=str(b.poles), label_pos=b.label_pos, folder=b.folder,
                    terminal_text_editable=_fmt(b.terminal_text_editable))
    for k, v in b.data.items():
        ET.SubElement(el, "data", name=k, value=str(v))
    for l in b.layers.values():
        _layer_to_xml(el, l, "blocklayer")
    ents = ET.SubElement(el, "entities")
    for e in b.entities:
        ents.append(ent_to_xml(e))
    for s in b.slots:
        ET.SubElement(el, "slot", terminal=s.terminal, x=_fmt(s.x), y=_fmt(s.y),
                      num_dx=_fmt(s.num_dx), num_dy=_fmt(s.num_dy))
    return el


def block_from_xml(el: ET.Element) -> m.BlockDef:
    b = m.BlockDef(el.get("name"), el.get("description", ""),
                   el.get("part_number", ""), el.get("tag_prefix", ""),
                   el.get("hyperlink", ""), el.get("manufacturer", ""),
                   increment=int(el.get("increment", "0")), connector=int(el.get("connector", "0")),
                   prefix_rule=el.get("prefix_rule", ""),
                   poles=int(el.get("poles", "1")), label_pos=el.get("label_pos", "right"), folder=el.get("folder", ""),
                   terminal_text_editable=el.get("terminal_text_editable") == "1")
    for d in el.findall("data"):
        b.data[d.get("name")] = d.get("value")
    for l in el.findall("blocklayer"):
        b.layers[l.get("name")] = _layer_from_xml(l)
    for e in el.find("entities"):
        b.entities.append(ent_from_xml(e))
    for s in el.findall("slot"):
        b.slots.append(m.Slot(s.get("terminal"), float(s.get("x")), float(s.get("y")),
                              float(s.get("num_dx")), float(s.get("num_dy"))))
    return b


# ---- project --------------------------------------------------------------
def _xml_bytes(el) -> bytes:
    ET.indent(el)
    return ET.tostring(el, encoding="utf-8", xml_declaration=True)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def save_project(p: m.Project, path) -> None:
    root = ET.Element("project", schema_version=str(p.schema_version),
                      name=p.name, lead_zero_suppress=_fmt(p.lead_zero_suppress))
    lay = ET.SubElement(root, "layers")
    for l in p.layers.values():
        ET.SubElement(lay, "layer", name=l.name, color=str(l.color), kind=l.kind,
                      numbered=_fmt(l.numbered), scheme=l.scheme,
                      linetype=l.linetype, lineweight=_fmt(l.lineweight), phase=l.phase)
    ET.SubElement(root, "info", **{k: str(v) for k, v in p.info.items()})
    pr = ET.SubElement(root, "prefix_rules")
    for r in p.prefix_rules:
        ET.SubElement(pr, "rule", name=r.name, pattern=r.pattern, if_true=r.if_true, if_false=r.if_false)
    sc = ET.SubElement(root, "schemes")
    for k, v in p.schemes.items():
        ET.SubElement(sc, "scheme", name=k, pattern=v)
    bf = ET.SubElement(root, "block_folders")
    for f in p.block_folders:
        ET.SubElement(bf, "folder", path=f)
    tst = ET.SubElement(root, "text_styles")
    for ts in p.text_styles.values():
        a = dict(name=ts.name, font=ts.font, height=_fmt(ts.height), align=ts.align)
        if ts.color is not None:
            a["color"] = str(ts.color)
        ET.SubElement(tst, "text_style", **a)
    pre = ET.SubElement(root, "multiline_presets")
    for mp in p.multiline_presets.values():
        pe = ET.SubElement(pre, "preset", name=mp.name, spacing=_fmt(mp.spacing))
        for ln, col, lab in zip(mp.layers, mp.colors, mp.labels):
            ET.SubElement(pe, "layer", name=ln, color=str(col), label=lab)
    pages = ET.SubElement(root, "pages")
    for pg in sorted(p.sheets):
        ET.SubElement(pages, "page", number=m.page_str(pg), file=f"sheets/{pg:02d}.xml")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.xml", _xml_bytes(root))
        for pg, s in sorted(p.sheets.items()):
            z.writestr(f"sheets/{pg:02d}.xml", _xml_bytes(sheet_to_xml(s)))
        for name, b in p.blocks.items():
            z.writestr(f"library/{_safe(name)}.xml", _xml_bytes(block_to_xml(b)))
        for name, t in p.templates.items():
            tel = sheet_to_xml(t)
            tel.set("template_name", name)           # file names are sanitised; keep the real name
            z.writestr(f"templates/{_safe(name)}.xml", _xml_bytes(tel))
        for apath, data in p.assets.items():
            z.writestr(f"assets/{apath}", data)


def load_project(path) -> m.Project:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("project.xml"))
        ver = int(root.get("schema_version", "0"))
        if ver > m.SCHEMA_VERSION:
            raise ValueError(f"project schema {ver} is newer than supported {m.SCHEMA_VERSION}")
        p = m.Project(root.get("name", ""), lead_zero_suppress=root.get("lead_zero_suppress") == "1",
                      schema_version=ver)
        for l in root.find("layers"):
            p.layers[l.get("name")] = m.Layer(l.get("name"), int(l.get("color")),
                                              l.get("kind"), l.get("numbered") == "1",
                                              l.get("scheme", ""), l.get("linetype", "continuous"),
                                              float(l.get("lineweight", "0")), l.get("phase", ""))
        info = root.find("info")
        if info is not None:
            p.info = dict(info.attrib)
        pr = root.find("prefix_rules")
        if pr is not None:
            p.prefix_rules = [m.PrefixRule(r.get("name"), r.get("pattern", "<L|T>"), r.get("if_true", ""),
                                           r.get("if_false", "")) for r in pr]
        sc = root.find("schemes")
        if sc is not None:
            p.schemes = {x.get("name"): x.get("pattern", "") for x in sc}
        bf = root.find("block_folders")
        if bf is not None:
            p.block_folders = [f.get("path") for f in bf]
        tst = root.find("text_styles")
        if tst is not None:
            p.text_styles = {t.get("name"): m.TextStyle(
                t.get("name"), t.get("font", ""), float(t.get("height", "0.12")),
                int(t.get("color")) if t.get("color") is not None else None,
                t.get("align", "left")) for t in tst}
            p.text_styles.setdefault("Default", m.TextStyle("Default"))
        pre = root.find("multiline_presets")
        if pre is not None:
            p.multiline_presets = {pe.get("name"): m.MultilinePreset(
                pe.get("name"), [x.get("name") for x in pe.findall("layer")],
                float(pe.get("spacing", "0")),
                [int(x.get("color", "7")) for x in pe.findall("layer")],
                [x.get("label") or x.get("name") for x in pe.findall("layer")]) for pe in pre}
        for pg in root.find("pages"):
            s = sheet_from_xml(ET.fromstring(z.read(pg.get("file"))))
            p.sheets[s.page] = s
        for n in z.namelist():
            if n.startswith("library/") and n.endswith(".xml"):
                b = block_from_xml(ET.fromstring(z.read(n)))
                p.blocks[b.name] = b
            elif n.startswith("templates/") and n.endswith(".xml"):
                tel = ET.fromstring(z.read(n))
                p.templates[tel.get("template_name") or n[len("templates/"):-4]] = sheet_from_xml(tel)
            elif n.startswith("assets/") and not n.endswith("/"):
                p.assets[n[len("assets/"):]] = z.read(n)
    return p
